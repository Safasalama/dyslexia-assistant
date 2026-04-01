const themes = {
  "Classic Bone": {
    "--bg-color": "#F2EDE4",
    "--card-bg-color": "#F7F2EA",
    "--text-color": "#3A3530",
    "--title-color": "#3A2E25",
    "--nav-color": "#3A2E25",
    "--nav-text-color": "#F2EDE4",
    "--accent-color":"#b65243",
    "--input-bg-color": "#F5F0EB",
    "--btn-hover-color": "#a04835",
    "--success-color": "#28a745",
    "img": "./imgs/home-classic-theme.png"
  },
  "Dark reading mode": {
    "--bg-color": "#3D2535",
    "--card-bg-color": "#2A1A20",
    "--text-color": "#e6e6e9",
    "--title-color": "#f2f4f5",
    "--nav-color": "#1A1015",
    "--nav-text-color": "#f2f4f5",
    "--accent-color":"#b0bec5",
    "--input-bg-color": "#2b1a25",
    "--btn-hover-color": "#493a49",
    "--success-color": "#64b5f6",
    "img": "./imgs/home-dark-theme.png"
  },
  "Soft pastel": {
    "--bg-color": "#F5EFE6",
    "--card-bg-color": "#F5F0FF",
    "--text-color": "#394b64",
    "--title-color": "rgb(21, 19, 37)",
    "--nav-color": "#394b64",
    "--nav-text-color": "#F5EFE6",
    "--accent-color":"#79acd0",
    "--input-bg-color": "#f2faff",
    "--btn-hover-color": "#5a8ba8",
    "--success-color": "#81c784",
    "img": "./imgs/home-pastel-theme.png"
  }
};

function changeTheme(themeName) {
  const theme = themes[themeName];

  for (let varName in theme) {
    if (varName.startsWith("--")) {
      document.documentElement.style.setProperty(varName, theme[varName]);
    }
  }

  const img = document.getElementById("theme-img");
  if (img) img.src = theme.img;

  document.querySelectorAll(".theme-btn").forEach(b => b.classList.remove("active"));
  document.querySelector(`[data-theme="${themeName}"]`).classList.add("active");
  localStorage.setItem("theme", themeName);
}

document.addEventListener("DOMContentLoaded", () => {
  const saved = localStorage.getItem("theme") || "Classic Bone";
  changeTheme(saved);

  document.querySelectorAll(".theme-btn").forEach(btn => {
    btn.addEventListener("click", () => changeTheme(btn.dataset.theme));
  });
});
//show of all sections
const reveals = document.querySelectorAll(".reveal");

window.addEventListener("scroll", () => {
  reveals.forEach((el) => {
    const windowHeight = window.innerHeight;
    const elementTop = el.getBoundingClientRect().top;
    const visiblePoint = 100;

    if (elementTop < windowHeight - visiblePoint) {
      el.classList.add("active");
    }
  });
});
//connect process text button to ai 

// API Configuration
const API_BASE_URL = "http://127.0.0.1:8000";

// API Functions
async function callAPI(endpoint, text) {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text: text
      })
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error("API Error:", error);
    throw error;
  }
}

async function analyzeText(text) {
  return await callAPI("/analyze", text);
}

async function simplifyText(text) {
  return await callAPI("/simplify", text);
}

async function processText(text) {
  return await callAPI("/process", text);
}

// Main Send Functions
document.getElementById("submitBtn").addEventListener("click", () => sendTextToAI("process"));
document.getElementById("analyzeBtn").addEventListener("click", () => sendTextToAI("analyze"));
document.getElementById("simplifyBtn").addEventListener("click", () => sendTextToAI("simplify"));

async function sendTextToAI(actionType) {
  const text = document.getElementById("textInput").value;

  if (!text.trim()) {
    alert("Please enter some text");
    return;
  }

  document.getElementById("loadingSpinner").style.display = "block";

  try {
    let data;

    switch(actionType) {
      case "analyze":
        data = await analyzeText(text);
        break;
      case "simplify":
        data = await simplifyText(text);
        break;
      case "process":
        data = await processText(text);
        break;
      default:
        throw new Error("Unknown action type");
    }

    console.log(`Response from ${actionType}:`, data);

    document.getElementById("loadingSpinner").style.display = "none";

    showResult(data, actionType);

  } catch (error) {
    document.getElementById("loadingSpinner").style.display = "none";
    alert("Error processing text. Make sure the API server is running.");
    console.error(error);
  }
}
function showResult(data, actionType) {
  document.getElementById("resultsSection").style.display = "block";

  // Show additional buttons after successful processing
  if (actionType === "process") {
    document.getElementById("analyzeBtn").style.display = "inline-block";
    document.getElementById("simplifyBtn").style.display = "inline-block";
  }

  let resultHTML = "";

  switch(actionType) {
    case "analyze":
      resultHTML = `
        <h5 class="mb-3"><i class="fa-solid fa-search me-2"></i>Text Analysis Results</h5>
        <div class="mb-3">
          <strong>Overall Difficulty Score:</strong> ${data.overall_difficulty}/10
        </div>
        <div class="mb-3">
          <strong>Hardest Words:</strong>
          <div class="mt-2">
            ${data.hardest_words.length > 0 ?
              data.hardest_words.map(word => `<span class="badge bg-warning text-dark me-1">${word}</span>`).join('') :
              '<span class="text-muted">No difficult words found</span>'}
          </div>
        </div>
        <div class="mb-3">
          <strong>Word-by-Word Analysis:</strong>
          <div class="mt-2">
            ${Object.entries(data.words).map(([word, score]) =>
              `<span class="badge bg-secondary me-1 mb-1" title="Score: ${score.difficulty_score}">
                ${word} (${score.difficulty_score})
              </span>`
            ).join('')}
          </div>
        </div>
      `;
      break;

    case "simplify":
      resultHTML = `
        <h5 class="mb-3"><i class="fa-solid fa-magic me-2"></i>Simplified Text</h5>
        <div class="mb-3">
          <strong>Original Text:</strong>
          <p class="mt-2 p-2 bg-light rounded">${data.original || "N/A"}</p>
        </div>
        <div class="mb-3">
          <strong>Simplified Text:</strong>
          <p class="mt-2 p-2 bg-success text-white rounded">${data.simplified}</p>
        </div>
        ${data.improvement ? `
        <div class="mb-3">
          <strong>Readability Improvement:</strong> ${data.improvement}
        </div>` : ''}
      `;
      break;

    case "process":
      resultHTML = `
        <h5 class="mb-3"><i class="fa-solid fa-play me-2"></i>Complete Processing Results</h5>

        <div class="row">
          <div class="col-md-6">
            <h6>Original Text Analysis</h6>
            <p><strong>Difficulty:</strong> ${data.original_analysis.overall_difficulty}/10</p>
            <p><strong>Hard Words:</strong> ${data.original_analysis.hardest_words.join(", ") || "None"}</p>
          </div>
          <div class="col-md-6">
            <h6>Simplified Text Analysis</h6>
            <p><strong>Difficulty:</strong> ${data.simplified_analysis.overall_difficulty}/10</p>
            <p><strong>Hard Words:</strong> ${data.simplified_analysis.hardest_words.join(", ") || "None"}</p>
          </div>
        </div>

        <hr>

        <div class="mb-3">
          <strong>Simplified Text:</strong>
          <p class="mt-2 p-3 bg-success text-white rounded">${data.simplified}</p>
        </div>

        <div class="mb-3">
          <strong>Readability Improvement:</strong> ${data.flesch_improvement}
        </div>
      `;
      break;
  }

  document.getElementById("resultContent").innerHTML = resultHTML;
}
//show of sparkle effect on the get started button
const btn = document.querySelector('.footer-btn');
let lastSparkle = 0;

btn.addEventListener('mousemove', (e) => {
  const now = Date.now();
  if (now - lastSparkle < 300) return; 
  lastSparkle = now;

  const sparkle = document.createElement('span');
  sparkle.classList.add('sparkle');
  sparkle.textContent = ['✦', '★'][Math.floor(Math.random() * 2)];

  const rect = btn.getBoundingClientRect();
  sparkle.style.left = (e.clientX - rect.left + Math.random() * 20 - 10) + 'px';
  sparkle.style.top  = (e.clientY - rect.top  + Math.random() * 20 - 10) + 'px';

  btn.appendChild(sparkle);
  setTimeout(() => sparkle.remove(), 1000);

});