export type BinaryInput = Uint8Array | ArrayBuffer | Blob;

export async function binaryBytes(value: BinaryInput): Promise<Uint8Array> {
  if (value instanceof Uint8Array) return new Uint8Array(value);
  if (value instanceof ArrayBuffer) return new Uint8Array(value.slice(0));
  return new Uint8Array(await value.arrayBuffer());
}

/** Encode bytes without relying on Node's Buffer runtime. */
export function encodeBase64(value: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = "";
  for (let offset = 0; offset < value.length; offset += chunkSize) {
    const chunk = value.subarray(offset, offset + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

/** Decode base64 without relying on Node's Buffer runtime. */
export function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  const result = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    result[index] = binary.charCodeAt(index);
  }
  return result;
}
