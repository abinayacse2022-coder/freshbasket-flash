document.addEventListener('click', function(e) {
  // Increase quantity
  if (e.target.matches('.qty-increase')) {
    const ctrl = e.target.closest('.qty-controls');
    if (!ctrl) return;
    const input = ctrl.querySelector('.qty');
    const min = parseInt(input.getAttribute('min') || '0', 10);
    input.value = Math.max(min, Number(input.value || 0) + 1);
    // auto-submit/update if inside cart
    const form = e.target.closest('form');
    if (form && form.classList.contains('update-form')) {
      sendUpdate(form);
    }
  }

  // Decrease quantity
  if (e.target.matches('.qty-decrease')) {
    const ctrl = e.target.closest('.qty-controls');
    if (!ctrl) return;
    const input = ctrl.querySelector('.qty');
    const min = parseInt(input.getAttribute('min') || '0', 10);
    const next = Math.max(min, Number(input.value || 0) - 1);
    input.value = next;
    const form = e.target.closest('form');
    if (form && form.classList.contains('update-form')) {
      sendUpdate(form);
    }
  }
});

// Intercept add-to-cart and update forms to use fetch(JSON)
document.addEventListener('submit', function(e) {
  const form = e.target;
  if (form.classList.contains('add-form')) {
    e.preventDefault();
    sendAdd(form);
  } else if (form.classList.contains('update-form')) {
    e.preventDefault();
    sendUpdate(form);
  }
});

function sendAdd(form) {
  const pid = form.querySelector('input[name=product_id]').value;
  const qty = Number(form.querySelector('input[name=qty]').value || 1);
  fetch('/cart/add', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({product_id: pid, qty: qty})
  }).then(r => r.json()).then(data => {
    // flash minimal feedback
    const btn = form.querySelector('.add-cart');
    if (btn) {
      const old = btn.innerText;
      btn.innerText = 'Added';
      setTimeout(()=> btn.innerText = old, 1200);
    }
  }).catch(err => console.error('Add failed', err));
}

function sendUpdate(form) {
  const pid = form.querySelector('input[name=product_id]').value;
  const qty = Number(form.querySelector('input[name=qty]').value || 0);
  fetch('/cart/update', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({product_id: pid, qty: qty})
  }).then(r => r.json()).then(data => {
    // reload to reflect totals and subtotals
    location.reload();
  }).catch(err => console.error('Update failed', err));
}
