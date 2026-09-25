<template>
  <!-- Explanations are read once, if at all. Folded at the end of the panel
       they explain, with a count, so a closed one still says there is
       something to read. Print opens every one of them. -->
  <details class="hint-fold" :class="{ 'hint-fold--caution': caution }">
    <summary class="hint-fold__head">
      {{ title }} <span v-if="count" class="hint-fold__count">{{ count }}</span>
    </summary>
    <div class="hint-fold__body"><slot /></div>
  </details>
</template>

<script>
export default {
  name: "HintFold",
  props: {
    title: { type: String, default: "Hinweise" },
    /** How many paragraphs the slot holds. Zero hides the number, which is
     *  right for a fold whose title already says what it holds. */
    count: { type: Number, default: 0 },
    /** A qualification of the figures above, not an operating note. */
    caution: { type: Boolean, default: false }
  }
};
</script>

<style scoped>
.hint-fold{ border-top: 1px solid var(--w2b-line-faint); font-size: var(--w2b-text-xs); }
.hint-fold__head{
  display: flex; align-items: center; gap: 6px;
  padding: var(--w2b-space-2) var(--w2b-space-4);
  color: var(--w2b-muted); cursor: pointer; list-style: none; user-select: none;
}
.hint-fold__head::-webkit-details-marker{ display: none; }
.hint-fold__head::before{
  content: ""; width: 6px; height: 6px; flex: none;
  border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor;
  transform: rotate(-45deg); transition: transform .15s;
}
.hint-fold[open] > .hint-fold__head::before{ transform: rotate(45deg); }
.hint-fold__head:hover{ color: var(--w2b-ink); }
.hint-fold__head:focus-visible{ outline: 2px solid var(--w2b-primary); outline-offset: -2px; }
.hint-fold--caution > .hint-fold__head{ color: var(--w2b-warning-text); font-weight: 600; }
.hint-fold__count{
  font-family: var(--w2b-font-mono); font-size: 10.5px; line-height: 1;
  padding: 3px 6px; border-radius: var(--w2b-radius-full);
  background: var(--w2b-surface-sunken); color: var(--w2b-muted);
}
.hint-fold__body{
  display: grid; gap: var(--w2b-space-2);
  padding: 0 var(--w2b-space-4) var(--w2b-space-3) calc(var(--w2b-space-4) + 12px);
  color: var(--w2b-graphite); line-height: 1.5;
}
.hint-fold__body :deep(p){ margin: 0; }
@media (prefers-reduced-motion: reduce){ .hint-fold__head::before{ transition: none; } }
</style>
