/**
 * SmartCart Shared Core Engine
 * Manages synchronized global state (Basket, Meal Plan, Theme, Postal Code),
 * cross-tab localStorage broadcast, drawer UI, modals, and common helpers.
 */

window.AppState = {
  selectedCity: localStorage.getItem('sc_city') || 'Edmonton',
  selectedProvince: localStorage.getItem('sc_province') || 'Alberta',
  postalCode: localStorage.getItem('sc_postal_code') || 'T5K 2X4',
  basket: JSON.parse(localStorage.getItem('sc_basket') || '[]'),
  mealPlan: JSON.parse(localStorage.getItem('sc_meal_plan') || '{}'),
  theme: localStorage.getItem('sc_theme') || 'dark',
  gasPriceAB: 1.62,
  gasPriceBC: 1.84,
  syncStatus: null
};

// --- Helper Functions ---
function getBannerColorClass(banner) {
  const b = (banner || '').toLowerCase();
  if (b.includes('frills')) return 'bg-yellow-400 text-yellow-950';
  if (b.includes('walmart')) return 'bg-blue-600 text-white';
  if (b.includes('superstore')) return 'bg-amber-500 text-white';
  if (b.includes('metro')) return 'bg-red-600 text-white';
  if (b.includes('sobeys')) return 'bg-emerald-700 text-white';
  if (b.includes('safeway')) return 'bg-rose-600 text-white';
  if (b.includes('freshco')) return 'bg-lime-600 text-white';
  if (b.includes('save-on') || b.includes('save on')) return 'bg-teal-700 text-white';
  if (b.includes('costco')) return 'bg-red-800 text-white';
  if (b.includes('giant tiger')) return 'bg-orange-600 text-white';
  if (b.includes('farm boy')) return 'bg-amber-700 text-white';
  if (b.includes('longo')) return 'bg-green-700 text-white';
  if (b.includes('loblaws')) return 'bg-red-700 text-white';
  if (b.includes('zehrs')) return 'bg-blue-700 text-white';
  if (b.includes('t&t')) return 'bg-emerald-800 text-white';
  return 'bg-slate-700 text-white';
}

function formatCurrency(num) {
  return '$' + (Number(num) || 0).toFixed(2);
}

// --- Toast System ---
function showToast(msg, icon = 'fa-circle-check') {
  let toast = document.getElementById('toastNotice');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toastNotice';
    toast.className = 'fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl bg-sc-navy text-white shadow-2xl border border-white/20 transition-all duration-300 opacity-0 translate-y-4 pointer-events-none';
    toast.innerHTML = `
      <div id="toastIcon" class="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center text-sc-emerald flex-shrink-0">
        <i class="fa-solid ${icon}"></i>
      </div>
      <div class="text-sm font-bold" id="toastMessage">${msg}</div>
    `;
    document.body.appendChild(toast);
  } else {
    const msgEl = document.getElementById('toastMessage');
    const iconEl = document.getElementById('toastIcon');
    if (msgEl) msgEl.innerText = msg;
    if (iconEl) iconEl.innerHTML = `<i class="fa-solid ${icon}"></i>`;
  }

  toast.classList.remove('opacity-0', 'translate-y-4', 'pointer-events-none');
  toast.classList.add('opacity-100', 'translate-y-0');

  clearTimeout(window._toastTimeout);
  window._toastTimeout = setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0');
    toast.classList.add('opacity-0', 'translate-y-4', 'pointer-events-none');
  }, 2800);
}

// --- Theme Management ---
function initTheme() {
  const isDark = AppState.theme !== 'light';
  applyTheme(isDark);
}

function applyTheme(isDark) {
  if (isDark) {
    document.documentElement.classList.add('dark');
    AppState.theme = 'dark';
  } else {
    document.documentElement.classList.remove('dark');
    AppState.theme = 'light';
  }
  document.querySelectorAll('.theme-toggle-icon').forEach(el => {
    el.className = isDark ? 'fa-solid fa-moon text-sm theme-toggle-icon' : 'fa-solid fa-sun text-sm theme-toggle-icon';
  });
}

function toggleDarkMode() {
  const nextDark = AppState.theme !== 'dark';
  localStorage.setItem('sc_theme', nextDark ? 'dark' : 'light');
  applyTheme(nextDark);
  showToast(nextDark ? 'Dark mode enabled' : 'Light mode enabled', nextDark ? 'fa-moon' : 'fa-sun');
}

// --- Basket Management & Multi-Tab Synchronization ---
function saveBasket() {
  localStorage.setItem('sc_basket', JSON.stringify(AppState.basket));
  updateBasketBadges();
  renderBasketDrawer();
  if (typeof window.onBasketChanged === 'function') {
    window.onBasketChanged();
  }
}

function updateBasketBadges() {
  const count = (AppState.basket || []).length;
  const badges = [
    document.getElementById('navCartCountBadge'),
    document.getElementById('floatingCartCountBadge'),
    document.getElementById('drawerBadgeCount')
  ];
  badges.forEach(b => {
    if (b) b.innerText = count;
  });
}

function openBasketDrawer() {
  const drawer = document.getElementById('basketDrawer');
  const backdrop = document.getElementById('basketDrawerBackdrop');
  if (!drawer || !backdrop) return;
  backdrop.classList.remove('hidden');
  drawer.classList.remove('translate-x-full');
  document.body.classList.add('overflow-hidden');
  renderBasketDrawer();
}

function closeBasketDrawer() {
  const drawer = document.getElementById('basketDrawer');
  const backdrop = document.getElementById('basketDrawerBackdrop');
  if (!drawer || !backdrop) return;
  drawer.classList.add('translate-x-full');
  setTimeout(() => {
    if (backdrop) backdrop.classList.add('hidden');
  }, 300);
  document.body.classList.remove('overflow-hidden');
}

function renderBasketDrawer() {
  const container = document.getElementById('drawerItemsList');
  if (!container) return;
  const badge = document.getElementById('drawerBadgeCount');
  const totalCostEl = document.getElementById('drawerTotalCost');
  const regCostEl = document.getElementById('drawerRegCost');
  const totalSavedEl = document.getElementById('drawerTotalSaved');

  const items = AppState.basket || [];
  if (badge) badge.innerText = items.length;

  let totalSale = 0;
  let totalReg = 0;
  items.forEach(it => {
    const qty = it.qty || 1;
    const sale = (it.price || it.sale_price || 0) * qty;
    const reg = (it.reg_price || it.regular_price || it.price || 0) * qty;
    totalSale += sale;
    totalReg += Math.max(sale, reg);
  });
  const saved = Math.max(0, totalReg - totalSale);

  if (totalCostEl) totalCostEl.innerText = formatCurrency(totalSale);
  if (regCostEl) regCostEl.innerText = formatCurrency(totalReg);
  if (totalSavedEl) totalSavedEl.innerText = saved > 0 ? `-${formatCurrency(saved)}` : '$0.00';

  if (items.length === 0) {
    container.innerHTML = `
      <div class="p-8 text-center text-sc-muted dark:text-slate-400 space-y-3">
        <div class="w-16 h-16 mx-auto rounded-3xl bg-sc-canvas dark:bg-white/5 flex items-center justify-center text-2xl text-sc-emerald">
          <i class="fa-solid fa-basket-shopping"></i>
        </div>
        <p class="font-bold text-base text-sc-ink dark:text-white">Your basket is empty</p>
        <p class="text-xs max-w-xs mx-auto">Add deals from Weekly Flyers, Price Compare, or type an item below.</p>
        <a href="/flyers" target="_blank" class="inline-flex items-center gap-1.5 mt-2 px-4 py-2 rounded-xl bg-sc-emerald text-sc-midnight font-bold text-xs hover:brightness-110">
          <span>Browse Weekly Flyers</span>
          <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
        </a>
      </div>`;
    return;
  }

  container.innerHTML = items.map((item, idx) => `
    <div class="p-4 rounded-2xl bg-sc-canvas dark:bg-sc-midnight border border-sc-border dark:border-sc-darkborder flex items-center justify-between gap-3 group">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <span class="font-bold text-sm text-sc-ink dark:text-white truncate">${item.name || item.item_name}</span>
          ${item.store ? `<span class="px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-wider ${getBannerColorClass(item.store)}">${item.store.split(' ')[0]}</span>` : ''}
        </div>
        <div class="text-xs text-sc-muted dark:text-slate-400 mt-0.5">
          ${formatCurrency(item.price || item.sale_price)}/ea
          ${item.package_size ? `• ${item.package_size}` : ''}
          • Line: <span class="font-bold text-sc-ink dark:text-slate-200">${formatCurrency((item.price || item.sale_price) * (item.qty || 1))}</span>
        </div>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <div class="flex items-center bg-white dark:bg-sc-darksurface rounded-xl border border-sc-border dark:border-sc-darkborder px-1.5 py-0.5">
          <button onclick="updateBasketQty(${idx}, -1)" class="w-6 h-6 flex items-center justify-center text-sc-muted hover:text-sc-ink dark:hover:text-white font-black">-</button>
          <span class="w-6 text-center font-bold text-xs text-sc-ink dark:text-white">${item.qty || 1}</span>
          <button onclick="updateBasketQty(${idx}, 1)" class="w-6 h-6 flex items-center justify-center text-sc-muted hover:text-sc-ink dark:hover:text-white font-black">+</button>
        </div>
        <button onclick="removeBasketItem(${idx})" class="p-2 text-sc-muted hover:text-red-500 transition-colors" title="Remove">
          <i class="fa-solid fa-trash text-xs"></i>
        </button>
      </div>
    </div>
  `).join('');
}

function updateBasketQty(idx, delta) {
  if (!AppState.basket[idx]) return;
  AppState.basket[idx].qty = Math.max(1, (AppState.basket[idx].qty || 1) + delta);
  saveBasket();
}

function removeBasketItem(idx) {
  if (!AppState.basket[idx]) return;
  const removed = AppState.basket.splice(idx, 1);
  saveBasket();
  if (removed[0]) showToast(`Removed "${removed[0].name || removed[0].item_name}"`);
}

function clearBasket() {
  if (!AppState.basket || AppState.basket.length === 0) return;
  if (!confirm('Clear all items from your SmartCart basket?')) return;
  AppState.basket = [];
  saveBasket();
  showToast('Basket cleared');
}

function handleDrawerQuickAdd() {
  const input = document.getElementById('drawerQuickAddInput');
  if (!input || !input.value.trim()) return;
  const val = input.value.trim();
  AppState.basket.push({
    name: val,
    price: 3.99,
    reg_price: 4.99,
    qty: 1,
    store: 'Supermarket',
    category: 'Groceries'
  });
  saveBasket();
  input.value = '';
  showToast(`Added "${val}" to basket`);
}

function runOptimizerFromDrawer() {
  closeBasketDrawer();
  if (window.location.pathname === '/optimizer' || window.location.pathname.endsWith('optimizer.html')) {
    if (typeof runBasketOptimization === 'function') {
      runBasketOptimization();
    }
  } else {
    window.open('/optimizer', '_blank');
  }
}

// --- Cross-Tab Real-time Sync ---
window.addEventListener('storage', (e) => {
  if (e.key === 'sc_basket') {
    try {
      AppState.basket = JSON.parse(e.newValue || '[]');
      updateBasketBadges();
      renderBasketDrawer();
      if (typeof window.onBasketChanged === 'function') {
        window.onBasketChanged();
      }
    } catch(err){}
  }
  if (e.key === 'sc_theme') {
    applyTheme(e.newValue === 'dark');
  }
  if (e.key === 'sc_city' || e.key === 'sc_postal_code') {
    AppState.selectedCity = localStorage.getItem('sc_city') || 'Edmonton';
    AppState.postalCode = localStorage.getItem('sc_postal_code') || 'T5K 2X4';
    if (typeof window.onLocationChanged === 'function') {
      window.onLocationChanged();
    }
  }
});

// --- Store Sync Modal & Indicator ---
async function loadSyncStatus() {
  try {
    const res = await fetch('/api/sync/status');
    const data = await res.json();
    AppState.syncStatus = data;
    const stores = Number(data.stores_indexed) || 0;
    const badge = document.getElementById('navSyncBadgeText');
    if (badge && stores) {
      badge.innerText = `Edmonton Beta · ${stores.toLocaleString()} Stores`;
    }
    document.querySelectorAll('[data-stores-indexed]').forEach(el => {
      if (stores) el.innerText = `${stores.toLocaleString()} Stores`;
    });
    const priced = document.getElementById('heroPricedStat');
    if (priced) {
      const cov = await (await fetch('/api/coverage/stats')).json();
      priced.innerText = (cov.stores_with_prices || 0).toLocaleString();
    }
  } catch (err) {
    console.warn('Sync status fetch notice:', err);
  }
}

function openSyncModal() {
  const m = document.getElementById('syncModal');
  if (m) m.classList.remove('hidden');
  loadSyncStatus();
}

function closeSyncModal() {
  const m = document.getElementById('syncModal');
  if (m) m.classList.add('hidden');
}

async function triggerManualSync() {
  const btn = document.getElementById('syncModalTriggerBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin mr-1.5"></i> Refreshing Supermarkets...';
  }
  try {
    const res = await fetch('/api/sync/refresh', { method: 'POST' });
    const data = await res.json();
    showToast(`Refreshed prices for ${(data.stores_count || 0).toLocaleString()} stores`);
    await loadSyncStatus();
  } catch (err) {
    showToast('Sync initiated in background');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-rotate mr-1.5"></i> Force Refresh Now';
    }
  }
}

// --- PRO Modal ---
function openProModal() {
  const m = document.getElementById('proModal');
  if (m) m.classList.remove('hidden');
}

function closeProModal() {
  const m = document.getElementById('proModal');
  if (m) m.classList.add('hidden');
}

// --- Mobile Navigation Menu ---
function toggleMobileMenu() {
  const drawer = document.getElementById('mobileNavDrawer');
  const icon = document.getElementById('mobileMenuIcon');
  if (!drawer) return;
  const isHidden = drawer.classList.contains('hidden');
  if (isHidden) {
    drawer.classList.remove('hidden');
    if (icon) icon.className = 'fa-solid fa-xmark text-base';
  } else {
    drawer.classList.add('hidden');
    if (icon) icon.className = 'fa-solid fa-bars text-base';
  }
}

// Global Keyboard Shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeBasketDrawer();
    closeSyncModal();
    closeProModal();
    if (typeof window.closeAllPageModals === 'function') {
      window.closeAllPageModals();
    }
  }
});

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  updateBasketBadges();
  loadSyncStatus();
});
