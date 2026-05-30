const form = document.querySelector("#certificate-form");
const statusBox = document.querySelector("#job-status");
const jobTitle = document.querySelector("#job-title");
const jobMessage = document.querySelector("#job-message");
const downloadLink = document.querySelector("#download-link");
const spinner = document.querySelector(".spinner");

function setSpinnerVisible(isVisible) {
  if (spinner) {
    spinner.hidden = !isVisible;
  }
}

function setLoading(message) {
  statusBox.hidden = false;
  downloadLink.hidden = true;
  setSpinnerVisible(true);
  jobTitle.textContent = "Generating";
  jobMessage.textContent = message;
  form.querySelector("button").disabled = true;
}

function setReady(url) {
  setSpinnerVisible(false);
  jobTitle.textContent = "Ready";
  jobMessage.textContent = "Your certificates are ready.";
  downloadLink.href = url;
  downloadLink.hidden = false;
  form.querySelector("button").disabled = false;
}

function setFailed(message) {
  setSpinnerVisible(false);
  jobTitle.textContent = "Failed";
  jobMessage.textContent = message;
  form.querySelector("button").disabled = false;
}

async function pollJob(statusUrl) {
  const response = await fetch(statusUrl, { credentials: "same-origin" });
  if (!response.ok) {
    setFailed("Could not read job status.");
    return;
  }
  const job = await response.json();
  jobMessage.textContent = job.message;
  if (job.status === "complete") {
    setReady(job.download_url);
    return;
  }
  if (job.status === "failed") {
    setFailed(job.message);
    return;
  }
  window.setTimeout(() => pollJob(statusUrl), 1200);
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setLoading("Uploading names file...");
    const response = await fetch("/api/jobs", {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
    });
    if (!response.ok) {
      let message = "Could not start certificate generation.";
      try {
        const error = await response.json();
        message = error.detail || message;
      } catch (_error) {
        // Keep the default message.
      }
      setFailed(message);
      return;
    }
    const job = await response.json();
    setLoading("Generating certificates...");
    pollJob(job.status_url);
  });
}
