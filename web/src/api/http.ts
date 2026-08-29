export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const res = await fetch(input, {
    ...init,
    credentials: "include",
    headers,
  });
  if (res.status === 401) {
    window.dispatchEvent(new Event("kiln:unauthorized"));
  }
  return res;
}
