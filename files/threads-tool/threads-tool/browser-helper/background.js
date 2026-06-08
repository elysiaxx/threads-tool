const GRAPHQL_URL = "https://www.threads.com/api/graphql";

function pick(value) {
  return Array.isArray(value) ? value[0] : value;
}

chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    const formData = details.requestBody?.formData || {};
    const docId = pick(formData.doc_id);
    const friendlyName =
      pick(formData.fb_api_req_friendly_name) ||
      pick(formData.friendly_name) ||
      "BarcelonaSearchResultsQuery";

    if (!docId) return;

    const variables = pick(formData.variables) || "";
    const looksLikeSearch =
      String(friendlyName).toLowerCase().includes("search") ||
      String(variables).includes('"query"') ||
      String(variables).includes("%22query%22");

    if (!looksLikeSearch) return;

    chrome.storage.local.set({
      threadsSearchDocId: String(docId),
      threadsSearchFriendlyName: String(friendlyName),
      threadsDocIdCapturedAt: new Date().toISOString(),
    });
  },
  { urls: [GRAPHQL_URL] },
  ["requestBody"]
);
