<template>
  <div v-if="total > limit" class="pager">
    <button type="button" class="btn btn--quiet btn--small" :disabled="offset === 0" @click="go(-1)">
      Zurück
    </button>
    <span class="pager__state">
      {{ first }}–{{ last }} von {{ num(total, 0) }}
    </span>
    <button type="button" class="btn btn--quiet btn--small" :disabled="last >= total" @click="go(1)">
      Weiter
    </button>
  </div>
  <p v-else-if="total > 0" class="hint pager__all">{{ num(total, 0) }} Einträge, das ist alles.</p>
</template>

<script>
/**
 * One page of a list, and where in the list it is.
 *
 * Every table in this area is paged from the first version rather than when it
 * starts to hurt: an instance with a thousand accounts would otherwise answer
 * with a megabyte of JSON and a page nobody can read, and that is exactly the
 * instance where somebody needs to look something up.
 *
 * Numbers rather than page numbers on purpose — „26–50 von 431“ says how much
 * is left, which is the question; „Seite 2“ does not.
 */
import { num } from "../../lib/format.js";

export default {
  name: "AdminPager",
  props: {
    total: { type: Number, default: 0 },
    offset: { type: Number, default: 0 },
    limit: { type: Number, default: 25 }
  },
  emits: ["move"],
  computed: {
    first() { return this.total === 0 ? 0 : this.offset + 1; },
    last() { return Math.min(this.offset + this.limit, this.total); }
  },
  methods: {
    num,
    go(direction) {
      this.$emit("move", Math.max(0, this.offset + direction * this.limit));
    }
  }
};
</script>

<style scoped>
.pager{ display: flex; align-items: center; gap: var(--w2b-space-3); }
.pager__state{ font-size: var(--w2b-text-xs); color: var(--w2b-muted); font-variant-numeric: tabular-nums; }
.pager__all{ margin: 0; }
</style>
