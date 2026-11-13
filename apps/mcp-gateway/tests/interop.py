# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Offline bidirectional compatibility with the deployed Python vault format."""
import json
import sys
from pathlib import Path
from cryptography.fernet import Fernet
from gateway import Vault
root=Path('/interop')
if sys.argv[1]=='seed':
    assert not (root/'fixture.json').exists()
    key=Fernet.generate_key().decode()
    pending={'path':'workspaces/test/projects/11111111-1111-4111-8111-111111111111/work-items/',
             'payload':{'append':True,'title':'讨论 😀','description_markdown':'Private discussion'},'prepared_by':'plane'}
    identifier='22222222-2222-4222-8222-222222222222'
    vault=Vault(str(root/'vault.sqlite'),key)
    vault.prepare('compat-user',pending,identifier)
    (root/'fixture.json').write_text(json.dumps({'key':key,'pending':pending,'id':identifier}))
else:
    fixture=json.loads((root/'fixture.json').read_text());ts=json.loads((root/'typescript.json').read_text())
    vault=Vault(str(root/'vault.sqlite'),fixture['key'])
    assert vault.prepared('compat-user',ts['data'])==ts['id']
    assert vault.decision('compat-user',ts['id'])==ts['data']
    print('TypeScript-created encrypted decisions and audit read by Python; rollback compatible.')
