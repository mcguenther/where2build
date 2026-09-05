<template>
  <div class="stack">
    <div class="page-head">
      <div>
        <p class="eyebrow">Adresse</p>
        <h1>Diese Seite gibt es nicht</h1>
        <p class="page-head__sub">
          Unter <span class="mono">{{ $route.fullPath }}</span> liegt nichts. Vermutlich ein
          Tippfehler oder ein Link aus einer älteren Fassung.
        </p>
      </div>
    </div>

    <div class="empty-card">
      <p>Von der Übersicht aus geht es zu allen Bereichen.</p>
      <RouterLink class="btn" :to="{ name: 'plots' }">Zur Übersicht</RouterLink>
    </div>
  </div>
</template>

<script>
export default { name: "NotFoundView" };
</script>

<style scoped>
.page-head__sub{ max-width: 62ch; }
.page-head__sub .mono{ overflow-wrap: anywhere; }
.empty-card{
  border: 1px dashed var(--w2b-line); border-radius: var(--w2b-radius-m);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--w2b-space-3); padding: var(--w2b-space-6) var(--w2b-space-5); text-align: center; min-height: 200px;
}
.empty-card p{ color: var(--w2b-muted); font-size: var(--w2b-text-s); }
.empty-card .btn{ text-decoration: none; }
</style>
