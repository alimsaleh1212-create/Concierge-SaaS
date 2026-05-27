(function () {
  var script = document.currentScript;
  if (!script) {
    var scripts = document.getElementsByTagName("script");
    script = scripts[scripts.length - 1];
  }

  if (!script) {
    console.error("Concierge widget loader: script tag not found");
    return;
  }

  var widgetId = script.getAttribute("data-widget-id");
  if (!widgetId) {
    console.error("Concierge widget loader: data-widget-id is required");
    return;
  }

  var origin = window.location.origin;
  var apiOrigin = new URL(script.src).origin;
  var tokenUrl = apiOrigin + "/auth/widget-token";
  var bundleUrl = apiOrigin + "/widget-bundle/index.js";

  fetch(tokenUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      widget_id: widgetId,
      origin: origin,
    }),
  })
    .then(function (response) {
      if (response.status === 403) {
        console.error("Widget not allowed on this origin");
        return null;
      }
      if (!response.ok) {
        console.error("Widget token request failed");
        return null;
      }
      return response.json();
    })
    .then(function (data) {
      if (!data || !data.token) {
        return;
      }

      var iframe = document.createElement("iframe");
      iframe.src = bundleUrl;
      iframe.style.position = "fixed";
      iframe.style.bottom = "24px";
      iframe.style.right = "24px";
      iframe.style.width = "360px";
      iframe.style.height = "520px";
      iframe.style.border = "none";
      iframe.style.zIndex = "9999";
      iframe.style.background = "transparent";

      iframe.addEventListener("load", function () {
        iframe.contentWindow.postMessage(
          {
            type: "CONCIERGE_INIT",
            token: data.token,
            widget_id: widgetId,
            api_origin: apiOrigin,
          },
          "*"
        );
      });

      document.body.appendChild(iframe);
    })
    .catch(function (error) {
      console.error("Widget loader error", error);
    });
})();
