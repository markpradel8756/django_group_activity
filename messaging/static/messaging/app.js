"use strict";

document.documentElement.classList.add("js");

const menu = document.querySelector("[data-nav-toggle]");
if (menu) {
  const sidebar = document.getElementById("sidebar");
  const scrim = document.querySelector(".nav-scrim");
  const workspace = document.querySelector(".workspace");
  const mobile = window.matchMedia("(max-width: 740px)");
  const closeButton = sidebar.querySelector("[data-nav-close]");

  function setMenu(open, returnFocus = false) {
    sidebar.classList.toggle("open", open);
    sidebar.inert = mobile.matches && !open;
    workspace.inert = open;
    scrim.hidden = !open;
    menu.setAttribute("aria-expanded", String(open));
    if (open) closeButton.focus();
    if (returnFocus && mobile.matches) menu.focus();
  }

  menu.addEventListener("click", () => setMenu(true));
  for (const control of document.querySelectorAll("[data-nav-close]")) {
    control.addEventListener("click", () => setMenu(false, true));
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.classList.contains("open")) setMenu(false, true);
  });
  mobile.addEventListener("change", () => setMenu(false));
  setMenu(false);
}

const protectedForms = document.querySelectorAll("[data-submit-once]");
for (const form of protectedForms) {
  const button = form.querySelector("button[type='submit']");
  const label = button.querySelector("[data-button-label]");
  const originalLabel = label.textContent;

  form.addEventListener("submit", (event) => {
    if (button.disabled) {
      event.preventDefault();
      return;
    }
    button.disabled = true;
    label.textContent = button.dataset.loadingLabel;
    form.setAttribute("aria-busy", "true");
  });
  // The browser can restore this page after a user presses Back.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    button.disabled = false;
    label.textContent = originalLabel;
    form.removeAttribute("aria-busy");
  });
}

const message = document.getElementById("id_body");
if (message) {
  const recipient = document.getElementById("id_recipient");
  const savedContact = document.getElementById("saved-contact");
  const previewNumber = document.getElementById("preview-number");
  const previewBody = document.getElementById("preview-body");
  const characters = document.getElementById("sms-chars");
  const segments = document.getElementById("sms-segments");
  const limitWarning = document.getElementById("sms-over-limit");
  const encoding = JSON.parse(document.getElementById("sms-encoding").textContent);
  const utf8 = new TextEncoder();

  function updatePreview() {
    const body = [...message.value];
    const gsm = body.every((char) => encoding.basic.includes(char) || encoding.extension.includes(char));
    const sizes = body.map((char) => gsm ? (encoding.extension.includes(char) ? 2 : 1) : char.length);
    const units = sizes.reduce((total, size) => total + size, 0);
    const singleLimit = gsm ? 160 : 70;
    const multipartLimit = gsm ? 153 : 67;
    // textbee's modified UTF-8 adds two bytes for supplementary characters and one for NUL.
    const byteCount = utf8.encode(message.value).length + body.reduce(
      (extra, char) => extra + (char.length === 2 ? 2 : Number(char === "\0")), 0
    );
    let count = units > 0 ? 1 : 0;
    if (units > singleLimit) {
      let used = 0;
      for (const size of sizes) {
        if (used + size > multipartLimit) {
          count += 1;
          used = 0;
        }
        used += size;
      }
    }

    previewNumber.textContent = recipient.value.trim() || "Recipient number";
    previewBody.textContent = message.value.trim() ? message.value : "Your message will appear here.";
    characters.textContent = `${body.length.toLocaleString()} characters · ${byteCount.toLocaleString()} / ${encoding.byteLimit.toLocaleString()} bytes`;
    segments.textContent = `${count} ${count === 1 ? "segment" : "segments"} · ${gsm ? "GSM-7" : "Unicode"}`;
    limitWarning.hidden = byteCount <= encoding.byteLimit;
  }

  if (savedContact) {
    savedContact.addEventListener("change", () => {
      if (savedContact.value) recipient.value = savedContact.value;
      updatePreview();
    });
    recipient.addEventListener("input", () => {
      const matches = Array.from(savedContact.options).some((option) => option.value === recipient.value);
      savedContact.value = matches ? recipient.value : "";
    });
  }
  message.addEventListener("input", updatePreview);
  recipient.addEventListener("input", updatePreview);
  window.addEventListener("pageshow", updatePreview);
  updatePreview();
}
