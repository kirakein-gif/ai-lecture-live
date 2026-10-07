document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-copy]');
  if (!btn) return;
  const text = btn.dataset.copy || '';
  try {
    await navigator.clipboard.writeText(text);
    const old = btn.textContent;
    btn.textContent = '복사됨';
    setTimeout(() => btn.textContent = old, 1200);
  } catch (_) {
    window.prompt('아래 주소를 복사하세요.', text);
  }
});
