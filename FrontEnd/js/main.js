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