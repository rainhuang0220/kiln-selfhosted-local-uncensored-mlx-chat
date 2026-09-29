(function () {
  var p = localStorage.getItem("kiln-theme") || "light";
  var dark =
    p === "dark" ||
    (p === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();
