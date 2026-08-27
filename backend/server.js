const express = require('express');
const cors = require('cors');
const multer = require('multer');
const { v4: uuidv4 } = require('uuid');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn, spawnSync } = require('child_process');

const app = express();
app.use(cors());
app.use(express.json());

const TEMP_ROOT = path.join(os.tmpdir(), 'criator');
const UPLOAD_DIR = path.join(TEMP_ROOT, 'uploads');
const JOBS_DIR = path.join(TEMP_ROOT, 'jobs');
const DOWNLOAD_TTL_MS = 30 * 60 * 1000;
const PROCESS_TIMEOUT_MS = 45 * 60 * 1000;
const MAX_LOG_LINES = 250;

fs.mkdirSync(UPLOAD_DIR, { recursive: true });
fs.mkdirSync(JOBS_DIR, { recursive: true });

function isInsideTemp(targetPath) {
  const root = path.resolve(TEMP_ROOT);
  const target = path.resolve(targetPath);
  return target === root || target.startsWith(root + path.sep);
}

function safeRemove(targetPath) {
  if (!targetPath || !isInsideTemp(targetPath)) return;
  try {
    fs.rmSync(targetPath, { recursive: true, force: true });
  } catch (err) {
    console.warn('Falha ao limpar temporario:', targetPath, err.message);
  }
}

function fileExists(targetPath) {
  try {
    return fs.existsSync(targetPath);
  } catch {
    return false;
  }
}

function resolvePython() {
  const candidates = [
    process.env.CRIATOR_PYTHON,
    path.join(__dirname, '..', 'ai', 'venv', 'Scripts', 'python.exe'),
    'python'
  ].filter(Boolean);

  for (const candidate of candidates) {
    const check = runCheck(candidate, ['--version'], { timeout: 4000 });
    if (check.ok) {
      return { command: candidate, version: check.output };
    }
  }
  return { command: 'python', version: 'python indisponivel' };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function estimateEta(job) {
  if (!job.startedAt || job.progress <= 0 || job.progress >= 100) return null;
  const elapsed = (Date.now() - job.startedAt) / 1000;
  const total = elapsed / (job.progress / 100);
  return Math.max(0, Math.round(total - elapsed));
}

function lastInterestingError(job) {
  const lines = job.logs
    .filter(entry => entry.stream === 'stderr' || entry.line.startsWith('ERROR:') || entry.line.includes('falhou'))
    .map(entry => entry.line);
  return lines.slice(-12).join('\n').trim();
}

class SimpleQueue {
  constructor() {
    this.jobs = [];
    this.processing = false;
    this.currentJob = null;
  }

  async add(name, data) {
    const job = {
      id: uuidv4(),
      name,
      data,
      status: 'waiting',
      progress: 0,
      step: 'queued',
      message: 'Aguardando na fila',
      result: null,
      error: null,
      logs: [],
      stdoutBuffer: '',
      stderrBuffer: '',
      startedAt: null,
      finishedAt: null,
      expiresAt: null,
      process: null,
      cleanupTimer: null,
      timeoutTimer: null,
      cancelRequested: false
    };
    this.jobs.push(job);
    this.processNext();
    return job;
  }

  async processNext() {
    if (this.processing) return;
    const waiting = this.jobs.find(job => job.status === 'waiting');
    if (!waiting) return;

    this.processing = true;
    this.currentJob = waiting;
    waiting.status = 'active';
    waiting.step = 'starting';
    waiting.message = 'Iniciando pipeline';
    waiting.startedAt = Date.now();

    const { videoPath, audioPath, resolution, duration, fps, modo, outputFinal, jobDir, projectId } = waiting.data;
    const python = resolvePython();
    const aiPath = path.join(__dirname, '..', 'ai', 'pipeline.py');
    fs.mkdirSync(jobDir, { recursive: true });

    return new Promise((resolve) => {
      let settled = false;

      const finish = (code, err) => {
        if (settled) return;
        settled = true;

        if (waiting.timeoutTimer) {
          clearTimeout(waiting.timeoutTimer);
          waiting.timeoutTimer = null;
        }

        waiting.process = null;
        waiting.finishedAt = Date.now();

        if (waiting.cancelRequested) {
          waiting.status = 'canceled';
          waiting.step = 'canceled';
          waiting.message = 'Job cancelado';
          this.cleanupJob(waiting);
        } else if (code === 0 && fileExists(outputFinal)) {
          waiting.status = 'completed';
          waiting.progress = 100;
          waiting.step = 'completed';
          waiting.message = 'Video pronto para download';
          waiting.error = null;
          waiting.expiresAt = Date.now() + DOWNLOAD_TTL_MS;
          waiting.result = {
            downloadUrl: `/download/${waiting.id}`,
            filename: `${projectId}_final.mp4`
          };
          waiting.cleanupTimer = setTimeout(() => this.expireJob(waiting.id), DOWNLOAD_TTL_MS);
        } else {
          waiting.status = 'failed';
          waiting.step = 'failed';
          waiting.error = err ? err.message : lastInterestingError(waiting) || `Processo finalizou com codigo ${code}`;
          waiting.message = waiting.error.split('\n')[0] || 'Falha no processamento';
          this.cleanupJob(waiting);
        }

        this.processing = false;
        this.currentJob = null;
        resolve(waiting);
        setImmediate(() => this.processNext());
      };

      const child = spawn(
        python.command,
        [aiPath, videoPath, audioPath, resolution, String(duration), String(fps), outputFinal, modo],
        {
          cwd: jobDir,
          env: {
            ...process.env,
            PYTHONUNBUFFERED: '1'
          }
        }
      );

      waiting.process = child;
      waiting.timeoutTimer = setTimeout(() => {
        waiting.error = 'Timeout: o processo ficou tempo demais em execucao.';
        waiting.cancelRequested = true;
        this.killJobProcess(waiting);
      }, PROCESS_TIMEOUT_MS);

      child.stdout.on('data', data => this.handleOutput(waiting, data, 'stdout'));
      child.stderr.on('data', data => this.handleOutput(waiting, data, 'stderr'));
      child.on('error', err => finish(1, err));
      child.on('close', code => finish(code));
    });
  }

  handleOutput(job, data, stream) {
    const key = stream === 'stderr' ? 'stderrBuffer' : 'stdoutBuffer';
    job[key] += data.toString();
    const lines = job[key].split(/\r?\n/);
    job[key] = lines.pop() || '';
    for (const line of lines) {
      this.handleLine(job, line.trim(), stream);
    }
  }

  handleLine(job, line, stream) {
    if (!line) return;

    job.logs.push({ time: new Date().toISOString(), stream, line });
    if (job.logs.length > MAX_LOG_LINES) job.logs.splice(0, job.logs.length - MAX_LOG_LINES);

    const progressMatch = line.match(/^PROGRESS:(\d+)/);
    if (progressMatch) {
      job.progress = clamp(parseInt(progressMatch[1], 10), 0, 100);
      return;
    }

    if (line.startsWith('STATUS:')) {
      try {
        const payload = JSON.parse(line.slice('STATUS:'.length));
        if (Number.isFinite(payload.progress)) job.progress = clamp(payload.progress, 0, 100);
        if (payload.step) job.step = String(payload.step);
        if (payload.message) job.message = String(payload.message);
      } catch (err) {
        job.message = line;
      }
      return;
    }

    if (line.startsWith('ERROR:')) {
      try {
        const payload = JSON.parse(line.slice('ERROR:'.length));
        if (payload.step) job.step = String(payload.step);
        if (payload.message) {
          job.error = String(payload.message);
          job.message = String(payload.message).split('\n')[0];
        }
      } catch {
        job.error = line;
      }
      return;
    }

    if (/^\[[A-Z_]+\]/.test(line)) {
      job.message = line;
    }
  }

  getJob(id) {
    return this.jobs.find(job => job.id === id) || null;
  }

  getPublicJob(id) {
    const job = this.getJob(id);
    if (!job) return null;

    return {
      id: job.id,
      status: job.status,
      progress: job.progress,
      step: job.step,
      message: job.message,
      eta: estimateEta(job),
      error: job.error,
      downloadUrl: job.result ? job.result.downloadUrl : null,
      filename: job.result ? job.result.filename : null,
      expiresAt: job.expiresAt,
      logs: job.logs.slice(-80)
    };
  }

  getStatus() {
    return {
      processing: this.processing,
      current: this.currentJob ? { id: this.currentJob.id, progress: this.currentJob.progress, step: this.currentJob.step } : null,
      waiting: this.jobs.filter(job => job.status === 'waiting').length,
      active: this.jobs.filter(job => job.status === 'active').length,
      completed: this.jobs.filter(job => job.status === 'completed').length,
      failed: this.jobs.filter(job => job.status === 'failed').length,
      canceled: this.jobs.filter(job => job.status === 'canceled').length
    };
  }

  cancel(id) {
    const job = this.getJob(id);
    if (!job) return null;

    if (job.status === 'waiting') {
      job.cancelRequested = true;
      job.status = 'canceled';
      job.step = 'canceled';
      job.message = 'Job cancelado antes de iniciar';
      this.cleanupJob(job);
      return job;
    }

    if (job.status === 'active') {
      job.cancelRequested = true;
      job.step = 'canceling';
      job.message = 'Cancelando render';
      this.killJobProcess(job);
      return job;
    }

    return job;
  }

  killJobProcess(job) {
    if (!job.process) return;
    try {
      job.process.kill('SIGTERM');
      setTimeout(() => {
        if (job.process) {
          try {
            job.process.kill('SIGKILL');
          } catch {
            // ignored
          }
        }
      }, 3000);
    } catch (err) {
      job.error = err.message;
    }
  }

  markDownloaded(id) {
    const job = this.getJob(id);
    if (!job) return;
    job.status = 'downloaded';
    job.step = 'downloaded';
    job.message = 'Download concluido; temporarios removidos';
    this.cleanupJob(job);
  }

  expireJob(id) {
    const job = this.getJob(id);
    if (!job || job.status !== 'completed') return;
    job.status = 'expired';
    job.step = 'expired';
    job.message = 'Download expirado; temporarios removidos';
    this.cleanupJob(job);
  }

  cleanupJob(job) {
    if (job.cleanupTimer) {
      clearTimeout(job.cleanupTimer);
      job.cleanupTimer = null;
    }
    if (job.timeoutTimer) {
      clearTimeout(job.timeoutTimer);
      job.timeoutTimer = null;
    }

    safeRemove(job.data.jobDir);

    for (const inputPath of [job.data.videoPath, job.data.audioPath]) {
      if (!this.isInputReferenced(inputPath, job.id)) {
        safeRemove(inputPath);
      }
    }
  }

  isInputReferenced(inputPath, exceptJobId) {
    return this.jobs.some(job => {
      if (job.id === exceptJobId) return false;
      if (!['waiting', 'active', 'completed'].includes(job.status)) return false;
      return job.data.videoPath === inputPath || job.data.audioPath === inputPath;
    });
  }
}

const videoQueue = new SimpleQueue();
const upload = multer({ dest: UPLOAD_DIR, limits: { fileSize: 2 * 1024 * 1024 * 1024 } });

function getUploadedPair(req) {
  if (!req.files || !req.files.video || !req.files.audio) return null;
  return {
    videoPath: req.files.video[0].path,
    audioPath: req.files.audio[0].path
  };
}

function buildJobData(files, projectId, suffix) {
  const jobDir = path.join(JOBS_DIR, suffix ? `${projectId}-${suffix}` : projectId);
  fs.mkdirSync(jobDir, { recursive: true });
  
  return {
    jobDir,
    videoPath: files.videoPath,
    audioPath: files.audioPath,
    outputFinal: path.join(jobDir, 'final.mp4')
  };
}

app.post('/project', upload.fields([{ name: 'video' }, { name: 'audio' }]), async (req, res) => {
  const files = getUploadedPair(req);
  if (!files) return res.status(400).json({ error: 'Envie video e audio.' });

  const projectId = uuidv4();
  const resolution = req.body.resolution || '1080x1920';
  const duration = parseFloat(req.body.duration) || 30;
  const fps = 60;
  const modo = 'ritmico';
  const data = buildJobData(files, projectId);

  const job = await videoQueue.add('process', {
    projectId,
    ...data,
    resolution,
    duration,
    fps,
    modo
  });

  res.json({ projectId, jobId: job.id, status: 'queued' });
});

app.post('/project/auto', upload.fields([{ name: 'video' }, { name: 'audio' }]), async (req, res) => {
  const files = getUploadedPair(req);
  if (!files) return res.status(400).json({ error: 'Envie video e audio.' });

  const projectId = uuidv4();
  const versions = [
    { duration: 15, modo: 'ritmico' },
    { duration: 30, modo: 'legendado' },
    { duration: 60, modo: 'ritmico' }
  ];
  const jobs = [];

  for (const version of versions) {
    const data = buildJobData(files, projectId, `${version.duration}s`);
    const job = await videoQueue.add('process', {
      projectId: `${projectId}_${version.duration}s`,
      ...data,
      resolution: '1080x1920',
      duration: version.duration,
      fps: 60,
      modo: version.modo
    });
    jobs.push({ version: `${version.duration}s`, jobId: job.id });
  }

  res.json({ projectId, versions: jobs });
});

app.get('/job/:id', (req, res) => {
  const job = videoQueue.getPublicJob(req.params.id);
  if (!job) return res.status(404).json({ error: 'Not found' });
  res.json(job);
});

app.post('/job/:id/cancel', (req, res) => {
  const job = videoQueue.cancel(req.params.id);
  if (!job) return res.status(404).json({ error: 'Not found' });
  res.json(videoQueue.getPublicJob(job.id));
});

app.get('/download/:id', (req, res) => {
  const job = videoQueue.getJob(req.params.id);
  if (!job) return res.status(404).json({ error: 'Not found' });
  if (job.status === 'expired' || job.status === 'downloaded') {
    return res.status(410).json({ error: 'Download expirado.' });
  }
  if (job.status !== 'completed' || !fileExists(job.data.outputFinal)) {
    return res.status(409).json({ error: 'Video ainda nao esta pronto.' });
  }

  res.download(job.data.outputFinal, job.result.filename, err => {
    if (err) {
      console.error('Falha no download:', err.message);
      return;
    }
    videoQueue.markDownloaded(job.id);
  });
});

app.get('/queue/status', (req, res) => {
  res.json(videoQueue.getStatus());
});

function runCheck(command, args, options = {}) {
  try {
    const result = spawnSync(command, args, { encoding: 'utf8', timeout: options.timeout || 5000 });
    const maxOutput = options.maxOutput || 500;
    return {
      ok: result.status === 0,
      output: ((result.stdout || result.stderr || '').trim()).slice(0, maxOutput)
    };
  } catch (err) {
    return { ok: false, output: err.message };
  }
}

function getDiskInfo() {
  try {
    const stat = fs.statfsSync(TEMP_ROOT);
    return {
      freeGb: Number(((stat.bavail * stat.bsize) / 1024 / 1024 / 1024).toFixed(2)),
      totalGb: Number(((stat.blocks * stat.bsize) / 1024 / 1024 / 1024).toFixed(2))
    };
  } catch {
    return null;
  }
}

app.get('/health', (req, res) => {
  const pythonInfo = resolvePython();
  const pythonExe = pythonInfo.command;
  const ffmpeg = runCheck('ffmpeg', ['-version']);
  const ffmpegEncoders = runCheck('ffmpeg', ['-hide_banner', '-encoders'], { maxOutput: 200000 });
  const python = runCheck(pythonExe, ['--version']);
  const engine = runCheck(pythonExe, ['-c', 'import cv2, librosa, numpy; print("ok")'], { timeout: 15000 });

  res.json({
    status: 'ok',
    tempRoot: TEMP_ROOT,
    pythonCommand: pythonInfo.command,
    downloadTtlMinutes: DOWNLOAD_TTL_MS / 60000,
    processTimeoutMinutes: PROCESS_TIMEOUT_MS / 60000,
    ffmpeg: {
      ok: ffmpeg.ok,
      nvenc: ffmpegEncoders.ok && ffmpegEncoders.output.includes('h264_nvenc')
    },
    python,
    engine,
    disk: getDiskInfo(),
    memory: {
      freeGb: Number((os.freemem() / 1024 / 1024 / 1024).toFixed(2)),
      totalGb: Number((os.totalmem() / 1024 / 1024 / 1024).toFixed(2))
    },
    queue: videoQueue.getStatus()
  });
});

app.listen(5001, () => console.log('Criator Pro rodando em http://localhost:5001'));
