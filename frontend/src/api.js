const JSON_HEADERS = {
  'Content-Type': 'application/json',
};

async function parseResponse(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || 'Request failed.');
  }
  return payload;
}

export async function uploadFiles(files) {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const response = await fetch('/api/upload', {
    method: 'POST',
    body: formData,
  });
  return parseResponse(response);
}

export async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}