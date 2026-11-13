// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
import {
  createCipheriv,
  createDecipheriv,
  createHash,
  createHmac,
  randomBytes,
  randomUUID,
  timingSafeEqual,
} from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";

/** Match Python's sorted, ASCII JSON so existing decision fingerprints remain valid. */
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(", ")}]`;
  if (value !== null && typeof value === "object")
    return `{${Object.entries(value)
      .toSorted(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, item]) => `${canonical(key)}: ${canonical(item)}`)
      .join(", ")}}`;
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new Error("Invalid vault value");
  return encoded.replace(/[\u007f-\uffff]/g, (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`);
}
export const hash = (value: string) => createHash("sha256").update(value).digest("hex");

/** Fernet compatibility envelope; HMAC is verified before CBC decryption. */
export class Cipher {
  private key: Buffer;
  constructor(key: string) {
    this.key = Buffer.from(key, "base64url");
    if (this.key.length !== 32) throw new Error("Invalid vault key");
  }
  encode(value: unknown): Buffer {
    const header = Buffer.alloc(9);
    header[0] = 0x80;
    header.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 1000)), 1);
    const iv = randomBytes(16),
      cipher = createCipheriv("aes-128-cbc", this.key.subarray(16), iv);
    const body = Buffer.concat([header, iv, cipher.update(canonical(value)), cipher.final()]);
    return Buffer.from(
      Buffer.concat([body, createHmac("sha256", this.key.subarray(0, 16)).update(body).digest()])
        .toString("base64")
        .replaceAll("+", "-")
        .replaceAll("/", "_")
    );
  }
  decode(value: Uint8Array): unknown {
    const token = Buffer.from(Buffer.from(value).toString(), "base64url"),
      body = token.subarray(0, -32);
    if (
      token.length < 73 ||
      token[0] !== 0x80 ||
      !timingSafeEqual(token.subarray(-32), createHmac("sha256", this.key.subarray(0, 16)).update(body).digest())
    )
      throw new Error("Unreadable vault material");
    const cipher = createDecipheriv("aes-128-cbc", this.key.subarray(16), token.subarray(9, 25));
    return JSON.parse(Buffer.concat([cipher.update(token.subarray(25, -32)), cipher.final()]).toString());
  }
}

/** Preserve the deployed schema for bidirectional code rollback; never store MCP bearers. */
export class Vault {
  readonly db: DatabaseSync;
  readonly cipher: Cipher;
  constructor(path: string, key: string) {
    mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    this.cipher = new Cipher(key);
    this.db.exec(`PRAGMA busy_timeout=30000;
      CREATE TABLE IF NOT EXISTS tokens(key TEXT PRIMARY KEY,data BLOB NOT NULL,expires REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,connection TEXT NOT NULL,fingerprint TEXT NOT NULL,data BLOB NOT NULL,result BLOB,UNIQUE(connection,fingerprint));
      CREATE TABLE IF NOT EXISTS audit(trace TEXT PRIMARY KEY,connection TEXT,operation TEXT,status INTEGER,at REAL);`);
  }
  prepared(connection: string, data: unknown): string | undefined {
    const row = this.db
      .prepare("SELECT id FROM decisions WHERE connection=? AND fingerprint=?")
      .get(connection, hash(canonical(data))) as { id: string } | undefined;
    return row?.id;
  }
  prepare(connection: string, data: unknown, id: string): string {
    this.db
      .prepare("INSERT OR IGNORE INTO decisions(id,connection,fingerprint,data) VALUES(?,?,?,?)")
      .run(id, connection, hash(canonical(data)), this.cipher.encode(data));
    const result = this.prepared(connection, data);
    if (!result) throw new Error("Decision conflict");
    return result;
  }
  decision(connection: string, id: string): unknown {
    const row = this.db.prepare("SELECT data FROM decisions WHERE id=? AND connection=?").get(id, connection) as
      | { data: Uint8Array }
      | undefined;
    if (!row) throw new Error("Unknown decision for this connection");
    return this.cipher.decode(row.data as Uint8Array);
  }
  record(connection: string, operation: string, status: number): void {
    this.db
      .prepare("INSERT INTO audit VALUES(?,?,?,?,?)")
      .run(randomUUID(), connection, operation, status, Date.now() / 1000);
  }
  close(): void {
    this.db.close();
  }
}
