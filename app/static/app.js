const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileName = document.getElementById('fileName');
const uploadBtn = document.getElementById('uploadBtn');
const jdSection = document.getElementById('jdSection');
const analyzeBtn = document.getElementById('analyzeBtn');
const skipBtn = document.getElementById('skipBtn');
const jdText = document.getElementById('jdText');
const jdFileInput = document.getElementById('jdFileInput');
const jdFileName = document.getElementById('jdFileName');
const jdUploadArea = document.getElementById('jdUploadArea');
const statusCard = document.getElementById('statusCard');
const statusIcon = document.getElementById('statusIcon');
const statusText = document.getElementById('statusText');
const scoreSection = document.getElementById('scoreSection');
const scoreCircle = document.getElementById('scoreCircle');
const scoreNumber = document.getElementById('scoreNumber');
const scoreDesc = document.getElementById('scoreDesc');
const resultDiv = document.getElementById('result');
const stepsDiv = document.getElementById('steps');
const resetBtn = document.getElementById('resetBtn');

let selectedFile = null;
let selectedJdFile = null;
const MAX_FILE_SIZE = 10 * 1024 * 1024;

const STEPS = ['Uploading', 'Converting PDF', 'Extracting text', 'Analyzing with AI', 'Processed'];

// Upload area events
uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files[0]) selectFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) selectFile(fileInput.files[0]); });

function selectFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) { alert('Please upload a PDF file'); return; }
    if (file.size > MAX_FILE_SIZE) { alert('File too large. Max 10MB.'); return; }
    selectedFile = file;
    const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
    fileName.textContent = `${file.name} (${sizeMB} MB)`;
    uploadBtn.style.display = 'inline-block';
}

// Show JD section when upload button clicked
uploadBtn.addEventListener('click', () => {
    uploadBtn.style.display = 'none';
    jdSection.style.display = 'block';
});

// JD tabs
function switchTab(tab) {
    document.getElementById('tabText').classList.toggle('active', tab === 'text');
    document.getElementById('tabPdf').classList.toggle('active', tab === 'pdf');
    document.getElementById('jdTextArea').style.display = tab === 'text' ? 'block' : 'none';
    document.getElementById('jdPdfArea').style.display = tab === 'pdf' ? 'block' : 'none';
}
window.switchTab = switchTab;

// JD file upload
jdUploadArea.addEventListener('click', () => jdFileInput.click());
jdFileInput.addEventListener('change', () => {
    if (jdFileInput.files[0]) {
        selectedJdFile = jdFileInput.files[0];
        jdFileName.textContent = selectedJdFile.name;
    }
});

// Analyze with JD
analyzeBtn.addEventListener('click', () => startAnalysis(false));
skipBtn.addEventListener('click', () => startAnalysis(true));

async function startAnalysis(skipJd) {
    if (!selectedFile) return;
    analyzeBtn.disabled = true;
    skipBtn.disabled = true;
    jdSection.style.display = 'none';
    uploadArea.style.display = 'none';
    statusCard.style.display = 'block';
    scoreSection.style.display = 'none';
    scoreCircle.style.strokeDashoffset = 327;
    scoreNumber.textContent = '0';
    statusIcon.innerHTML = '<div class="spinner"></div>';
    statusText.textContent = 'Starting analysis...';
    resultDiv.innerHTML = '';
    stepsDiv.innerHTML = renderSteps('Uploading');

    const formData = new FormData();
    formData.append('file', selectedFile);

    if (!skipJd) {
        const jdTextVal = jdText.value.trim();
        if (jdTextVal) formData.append('jd_text', jdTextVal);
        if (selectedJdFile) formData.append('jd_file', selectedJdFile);
    }

    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Upload failed');
        const data = await res.json();
        pollStatus(data.file_id);
    } catch (err) {
        statusIcon.textContent = '❌';
        statusText.textContent = 'Upload failed — please try again';
        stepsDiv.innerHTML = '';
        resetButtons();
    }
}

function resetButtons() {
    analyzeBtn.disabled = false;
    skipBtn.disabled = false;
    uploadBtn.style.display = 'inline-block';
    jdSection.style.display = 'none';
}

function renderSteps(currentStatus) {
    const currentIdx = STEPS.indexOf(currentStatus);
    return STEPS.map((step, i) => {
        let icon = '<span class="step-icon pending">○</span>';
        let cls = 'step-pending';
        if (i < currentIdx) { icon = '<span class="step-icon done">✓</span>'; cls = 'step-done'; }
        else if (i === currentIdx && currentStatus !== 'Processed') { icon = '<span class="step-icon active"><div class="spinner-sm"></div></span>'; cls = 'step-active'; }
        else if (i === currentIdx && currentStatus === 'Processed') { icon = '<span class="step-icon done">✓</span>'; cls = 'step-done'; }
        return `<div class="step ${cls}">${icon}<span>${step}</span></div>`;
    }).join('');
}

function getScoreColor(score) {
    if (score >= 80) return '#00e676';
    if (score >= 60) return '#ffca28';
    if (score >= 40) return '#ff9800';
    return '#f44336';
}

function getScoreLabel(score) {
    if (score >= 80) return 'Excellent — your resume is well-optimized for ATS';
    if (score >= 60) return 'Good — some improvements needed';
    if (score >= 40) return 'Fair — significant changes recommended';
    return 'Needs work — major ATS issues found';
}

function animateScore(score) {
    scoreSection.style.display = 'block';
    const circumference = 327;
    const offset = circumference - (score / 100) * circumference;
    const color = getScoreColor(score);
    scoreCircle.style.stroke = color;
    scoreCircle.style.strokeDashoffset = offset;
    scoreNumber.style.color = color;
    scoreDesc.textContent = getScoreLabel(score);
    let current = 0;
    const step = Math.ceil(score / 40);
    const counter = setInterval(() => {
        current += step;
        if (current >= score) { current = score; clearInterval(counter); }
        scoreNumber.textContent = current;
    }, 30);
}

function renderMarkdown(text) {
    return text
        .replace(/## (.+)/g, '<h2>$1</h2>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^\* (.+)/gm, '<li>$1</li>')
        .replace(/^\- (.+)/gm, '<li>$1</li>')
        .replace(/((?:<li>.*<\/li>\s*)+)/g, '<ul>$1</ul>')
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

async function pollStatus(fileId) {
    const poll = setInterval(async () => {
        try {
            const res = await fetch(`/${fileId}`);
            if (!res.ok) throw new Error('Failed to fetch status');
            const data = await res.json();
            stepsDiv.innerHTML = renderSteps(data.status);
            statusText.textContent = data.status;

            if (data.status === 'Failed') {
                clearInterval(poll);
                statusIcon.textContent = '❌';
                statusText.textContent = 'Analysis failed';
                resultDiv.innerHTML = `<p style="color:#f44336">${data.result || 'Something went wrong.'}</p>`;
                resetForNewAnalysis();
            }

            if (data.status === 'Processed' && data.result) {
                clearInterval(poll);
                statusIcon.textContent = '✅';
                statusText.textContent = 'Analysis Complete';
                if (data.ats_score !== null && data.ats_score !== undefined) animateScore(data.ats_score);
                resultDiv.innerHTML = renderMarkdown(data.result);
                resetForNewAnalysis();
            }
        } catch (err) {
            clearInterval(poll);
            statusIcon.textContent = '❌';
            statusText.textContent = 'Connection lost — please refresh';
        }
    }, 2000);
}

function resetForNewAnalysis() {
    selectedFile = null;
    selectedJdFile = null;
    fileName.textContent = '';
    jdFileName.textContent = '';
    jdText.value = '';
    fileInput.value = '';
    jdFileInput.value = '';
    uploadBtn.style.display = 'none';
    uploadBtn.textContent = 'Analyze Resume';
    analyzeBtn.disabled = false;
    skipBtn.disabled = false;
    uploadArea.style.pointerEvents = 'auto';
    uploadArea.style.opacity = '1';
    resetBtn.style.display = 'inline-block';
}

resetBtn.addEventListener('click', () => {
    statusCard.style.display = 'none';
    scoreSection.style.display = 'none';
    resultDiv.innerHTML = '';
    stepsDiv.innerHTML = '';
    resetBtn.style.display = 'none';
    jdSection.style.display = 'none';
    uploadBtn.style.display = 'none';
    uploadArea.style.display = 'block';
    fileName.textContent = '';
    selectedFile = null;
    selectedJdFile = null;
    jdText.value = '';
    fileInput.value = '';
    jdFileInput.value = '';
    jdFileName.textContent = '';
});
