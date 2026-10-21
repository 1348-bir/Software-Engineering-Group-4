'use strict';
const start = Date.now(), timer = document.getElementById('timer');
const interval = setInterval(() => {
  const seconds = Math.floor((Date.now() - start) / 1000);
  timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}, 1000);
document.getElementById('quizForm')?.addEventListener('submit', () => clearInterval(interval));
