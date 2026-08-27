const API = "http://localhost:5001";
const $ = id => document.getElementById(id);

const els = {
  videoZone: $("videoZone"),
  audioZone: $("audioZone"),
  videoInput: $("videoInput"),
  audioInput: $("audioInput"),
  videoName: $("videoName"),
  audioName: $("audioName"),
  videoMeta: $("videoMeta"),
  audioMeta: $("audioMeta"),
  videoPreview: $("videoPreview"),
  audioPreview: $("audioPreview"),
  modo: $("modo"),
  resolution: $("resolution"),
  duration: $("duration"),
  fps: $("fps"),
  processBtn: $("processBtn"),
  cancelBtn: $("cancelBtn"),
  downloadLink: $("downloadLink"),
  progressSection: $("progressSection"),
  progressFill: $("progressFill"),
  statusStep: $("statusStep"),
  statusText: $("statusText"),
  etaText: $("etaText"),
  spinner: $("spinner"),
  logSection: $("logSection"),
  logToggle: $("logToggle"),
  logPanel: $("logPanel"),
  logCount: $("logCount"),
  errorBox: $("errorBox"),
  healthBadge: $("healthBadge")
};

let videoFile = null;
let audioFile = null;
let jobId = null;
let pollTimer = null;
const seenLogs = new Set();
const logs = [];

function fmtSize(bytes) {
  if (!bytes) return "0 MB";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function setBusy(isBusy) {
  els.processBtn.disabled = isBusy;
  els.cancelBtn.disabled = !isBusy;
  els.spinner.classList.toggle("hidden", !isBusy);
  els.processBtn.textContent = isBusy ? "Processando..." : "Criar video";
}

function showError(message) {
  els.errorBox.textContent = message || "";
  els.errorBox.classList.toggle("hidden", !message);
}

function setStatus(step, message, progress, eta) {
  const pct = Math.max(0, Math.min(Number(progress) || 0, 100));
  els.progressSection.classList.remove("hidden");
  els.statusStep.textContent = step || "status";
  els.statusText.textContent = message || "";
  els.progressFill.style.width = `${pct}%`;
  els.etaText.textContent = eta ? `ETA ${eta}s` : "ETA --";
}

function resetLogs() {
  logs.length = 0;
  seenLogs.clear();
  renderLogs();
}

function addLogs(items) {
  for (const item of items || []) {
    const key = `${item.time}|${item.stream}|${item.line}`;
    if (seenLogs.has(key)) continue;
    seenLogs.add(key);
    logs.push(item);
  }
  if (logs.length > 300) logs.splice(0, logs.length - 300);
  renderLogs();
}

function renderLogs() {
  els.logPanel.textContent = logs
    .map(item => `[${String(item.time || "").slice(11, 19)}] ${item.stream}: ${item.line}`)
    .join("\n");
  els.logCount.textContent = `${logs.length} linhas`;
  els.logSection.classList.toggle("hidden", logs.length === 0);
  els.logPanel.scrollTop = els.logPanel.scrollHeight;
}

function bindDropzone(zone, input, kind) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", event => {
    event.preventDefault();
    zone.classList.add("drag");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener("drop", event => {
    event.preventDefault();
    zone.classList.remove("drag");
    if (!event.dataTransfer.files.length) return;
    input.files = event.dataTransfer.files;
    input.dispatchEvent(new Event("change"));
  });
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    zone.classList.add("filled");
    if (kind === "video") {
      videoFile = file;
      els.videoName.textContent = file.name;
      els.videoMeta.textContent = `${file.type || "video"} | ${fmtSize(file.size)}`;
      els.videoPreview.src = url;
    } else {
      audioFile = file;
      els.audioName.textContent = file.name;
      els.audioMeta.textContent = `${file.type || "audio"} | ${fmtSize(file.size)}`;
      els.audioPreview.src = url;
    }
  });
}

async function startJob() {
  if (!videoFile || !audioFile) {
    showError("Selecione um video e um audio.");
    return;
  }

  showError("");
  resetLogs();
  setBusy(true);
  els.downloadLink.classList.add("hidden");
  setStatus("uploading", "Enviando arquivos...", 2, null);

  const form = new FormData();
  form.append("video", videoFile);
  form.append("audio", audioFile);
  form.append("resolution", els.resolution.value);
  form.append("duration", els.duration.value);
  form.append("fps", els.fps.value);
  form.append("modo", els.modo.value);

  try {
    const response = await fetch(`${API}/project`, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Falha ao iniciar job.");
    jobId = data.jobId;
    pollJob();
  } catch (error) {
    setBusy(false);
    showError(error.message);
    setStatus("failed", "Falha ao iniciar", 0, null);
  }
}

async function pollJob() {
  if (!jobId) return;
  try {
    const response = await fetch(`${API}/job/${jobId}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Job nao encontrado.");

    setStatus(data.step, data.message, data.progress, data.eta);
    addLogs(data.logs);

    if (data.status === "completed") {
      setBusy(false);
      els.downloadLink.href = `${API}${data.downloadUrl}`;
      els.downloadLink.download = data.filename || "criator_final.mp4";
      els.downloadLink.classList.remove("hidden");
      return;
    }

    if (["failed", "canceled", "expired"].includes(data.status)) {
      setBusy(false);
      if (data.error) showError(data.error);
      return;
    }

    pollTimer = setTimeout(pollJob, 900);
  } catch (error) {
    setBusy(false);
    showError(error.message);
  }
}

async function cancelJob() {
  if (!jobId) return;
  const response = await fetch(`${API}/job/${jobId}/cancel`, { method: "POST" });
  const data = await response.json();
  setStatus(data.step, data.message, data.progress, data.eta);
  addLogs(data.logs);
}

async function checkHealth() {
  try {
    const response = await fetch(`${API}/health`);
    const data = await response.json();
    const ok = Boolean(data.ffmpeg?.ok && data.python?.ok);
    els.healthBadge.className = `badge ${ok ? "on" : "off"}`;
    els.healthBadge.textContent = ok ? "Ambiente pronto" : "Ambiente incompleto";
  } catch {
    els.healthBadge.className = "badge off";
    els.healthBadge.textContent = "Backend offline";
  }
}

els.processBtn.addEventListener("click", startJob);
els.cancelBtn.addEventListener("click", cancelJob);
els.logToggle.addEventListener("click", () => els.logPanel.classList.toggle("hidden"));
addEventListener("beforeunload", () => {
  if (pollTimer) clearTimeout(pollTimer);
});

bindDropzone(els.videoZone, els.videoInput, "video");
bindDropzone(els.audioZone, els.audioInput, "audio");
checkHealth();
setStatus("ready", "Selecione video e audio para comecar.", 0, null);
