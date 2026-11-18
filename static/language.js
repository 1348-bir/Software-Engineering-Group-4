/* Preserve the current route and query parameters when changing language. */
function switchLang(lang) {
    const url = new URL(window.location.href);
    url.searchParams.set('lang', lang);
    window.location.href = url.toString();
}
