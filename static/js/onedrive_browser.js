document.addEventListener("DOMContentLoaded", () => {
  const previewCache = {};

  // select your file links — make sure they have class="file-preview" and data-id="{{ it.id }}"
  const els = document.querySelectorAll(".file-preview[data-id]");
  els.forEach(el => {
    const fileId = el.dataset.id;

    // pre‐fetch on hover
    el.addEventListener("mouseenter", () => {
      if (previewCache[fileId]) return;
      fetch(`/files/preview-url/${fileId}`)
        .then(res => res.json())
        .then(data => {
          if (data.preview_url) previewCache[fileId] = data.preview_url;
        })
        .catch(() => {
          /* ignore errors on hover */
        });
    });

    // open in new tab on click
    el.addEventListener("click", e => {
      e.preventDefault();

      // open a blank tab immediately (to avoid popup blockers)
      const tab = window.open("", "_blank");
      tab.document.write("<p style='font-family:sans-serif;'>🔄 Loading preview…</p>");

      const launch = url => {
        if (url) {
          tab.location = url;
        } else {
          tab.document.body.innerHTML = "<p>Unable to load preview.</p>";
        }
      };

      // if we already have it, go!
      if (previewCache[fileId]) {
        return launch(previewCache[fileId]);
      }

      // else fetch it now
      fetch(`/files/preview-url/${fileId}`)
        .then(res => res.json())
        .then(data => {
          const url = data.preview_url;
          if (url) previewCache[fileId] = url;
          launch(url);
        })
        .catch(() => launch(null));
    });
  });
});
