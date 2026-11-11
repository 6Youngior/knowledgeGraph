export const calls = [];
export default async function open(url, options) {
  calls.push({ url, options });
  return { unref() {} };
}
