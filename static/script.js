async function loadTranslations(lang) {
  try {
    const res = await fetch(`/static/locales/${lang}.json`);
    if (!res.ok) throw new Error("Translation not found");
    return await res.json();
  } catch {
    return {};
  }
}

function translatePage(translations) {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (translations[key]) {
      el.textContent = translations[key];
    }
  });


  const titleEl = document.getElementById("title");
  if (titleEl && translations["welcome"]) {
    titleEl.textContent = translations["welcome"];
  }
}


document.addEventListener("DOMContentLoaded", async () => {
  const lang = window.APP_LANG || "ru";
  const translations = await loadTranslations(lang);
  translatePage(translations);


  const langSelect = document.getElementById("lang-select");
  langSelect.value = lang;
  langSelect.addEventListener("change", () => {
    const selectedLang = langSelect.value;
    window.location.href = `/set_language/${selectedLang}`;
  });
});
