/* Only copies the user-requested public support contact, after a click. */
(() => {
  'use strict';
  const button = document.getElementById('copy-wechat');
  const contact = document.getElementById('wechat');
  const status = document.getElementById('copy-status');
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await navigator.clipboard.writeText(contact.textContent.trim());
      status.textContent = '已复制，在微信中搜索添加。';
    } catch (_) {
      const range = document.createRange();
      range.selectNodeContents(contact);
      const selection = window.getSelection();
      selection.removeAllRanges(); selection.addRange(range);
      contact.focus();
      status.textContent = '微信号已选中，请长按或手动复制。';
    } finally {
      button.disabled = false;
    }
  });
})();
