# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Bounded API reads pinned to a validated IP of an operator-registered host."""

import ipaddress
import json
import socket
from urllib.parse import urlencode, urlsplit

import certifi
import urllib3


class RepositoryError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def validate_instance(instance):
    """No user-controlled authority, URL credentials or implicit private networks."""
    for value in (instance.api_url, instance.web_url):
        try:
            url = urlsplit(value)
            if (
                url.scheme not in (["https", "http"] if instance.allow_http else ["https"])
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or any(c.isspace() for c in value)
                or "\\" in value
                or any(part in (".", "..") for part in url.path.split("/"))
                or "%" in url.netloc
            ):
                raise ValueError
            _ = url.port
        except ValueError:
            raise RepositoryError("invalid_instance") from None
    if instance.provider not in ("gitlab", "github"):
        raise RepositoryError("unsupported_provider")
    try:
        networks = [ipaddress.ip_network(value, strict=True) for value in instance.allowed_networks]
        if any(network.prefixlen == 0 for network in networks):
            raise ValueError
    except (ValueError, TypeError):
        raise RepositoryError("invalid_private_network_exception") from None
    return urlsplit(instance.api_url), networks


class RepositoryTransport:
    def __init__(self, instance, token=None):
        self.instance, self.token = instance, token

    def get(self, path, params=None):
        """Resolve once, validate every address, pin the connection; never redirect."""
        url, networks = validate_instance(self.instance)
        if not self.instance.enabled:
            raise RepositoryError("instance_disabled", 403)
        if not path.startswith("/") or path.startswith("//") or any(c in path for c in "?#\r\n\\"):
            raise RepositoryError("invalid_api_path")
        port = url.port or (443 if url.scheme == "https" else 80)
        try:
            addresses = list(
                dict.fromkeys(
                    result[4][0] for result in socket.getaddrinfo(url.hostname, port, type=socket.SOCK_STREAM)
                )
            )
        except OSError:
            raise RepositoryError("upstream_unavailable", 503) from None
        if not addresses:
            raise RepositoryError("upstream_unavailable", 503)
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                ip.is_multicast
                or ip.is_unspecified
                or (not ip.is_global and not any(ip in network for network in networks))
            ):
                raise RepositoryError("address_not_allowed", 403)
        headers = {
            "Host": url.netloc,
            "Accept": "application/json",
            "User-Agent": "Singularity-Repository-Reader",
            "Accept-Encoding": "identity",
        }
        if self.token:
            headers["PRIVATE-TOKEN" if self.instance.provider == "gitlab" else "Authorization"] = (
                self.token if self.instance.provider == "gitlab" else "Bearer " + self.token
            )
        options = dict(timeout=urllib3.Timeout(connect=5, read=20), retries=False)
        if url.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(
                addresses[0],
                port=port,
                server_hostname=url.hostname,
                assert_hostname=url.hostname,
                cert_reqs="CERT_REQUIRED",
                ca_certs=self.instance.ca_file or certifi.where(),
                **options,
            )
        else:
            pool = urllib3.HTTPConnectionPool(addresses[0], port=port, **options)
        target = url.path.rstrip("/") + path
        if params:
            target += "?" + urlencode(params)
        response = None
        try:
            response = pool.urlopen(
                "GET", target, headers=headers, redirect=False, preload_content=False, assert_same_host=False
            )
            if response.status in (401, 403):
                raise RepositoryError("upstream_access_denied", 403)
            if response.status == 404:
                raise RepositoryError("upstream_resource_invisible", 404)
            if response.status == 429:
                raise RepositoryError("upstream_rate_limited", 429)
            if 300 <= response.status < 400:
                raise RepositoryError("upstream_redirect_refused", 502)
            if response.status != 200:
                raise RepositoryError("upstream_unavailable", 503)
            body = response.read(2 * 1024 * 1024 + 1, decode_content=False)
            if len(body) > 2 * 1024 * 1024:
                raise RepositoryError("upstream_response_too_large", 422)
            return json.loads(body)
        except (urllib3.exceptions.HTTPError, OSError):
            raise RepositoryError("upstream_unavailable", 503) from None
        except (ValueError, UnicodeError):
            raise RepositoryError("invalid_upstream_response", 502) from None
        finally:
            if response is not None:
                response.close()
            pool.close()
