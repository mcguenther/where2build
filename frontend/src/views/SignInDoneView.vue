<template>
  <div class="stack">
    <div class="empty-card">
      <p>{{ note }}</p>
      <RouterLink v-if="stranded" class="btn" :to="{ name: 'home' }">Weiter zur Anwendung</RouterLink>
    </div>
  </div>
</template>

<script>
/**
 * The last step of signing in, and normally nobody sees it: the second window
 * lands here, tells the page that opened it, and closes.
 *
 * It has an address of its own because the backend can only send a browser to
 * one -- the whole exchange ends in a redirect, and this is where it points.
 * Somebody who arrives here without a window that opened them (a bookmark, a
 * pop-up that a browser turned into a tab) is not stuck: they are told, and
 * shown the way on.
 */
import { reportSignedIn } from "../lib/signIn.js";

export default {
  name: "SignInDoneView",
  data() {
    return { stranded: false };
  },
  computed: {
    note() {
      return this.stranded
        ? "Die Anmeldung ist abgeschlossen."
        : "Die Anmeldung ist abgeschlossen. Dieses Fenster schließt sich.";
    }
  },
  mounted() {
    this.stranded = !reportSignedIn();
  }
};
</script>

<style scoped>
.empty-card{
  border: 1px dashed var(--w2b-line); border-radius: var(--w2b-radius-m);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--w2b-space-3); padding: var(--w2b-space-6) var(--w2b-space-5); text-align: center; min-height: 200px;
}
.empty-card p{ color: var(--w2b-muted); font-size: var(--w2b-text-s); }
.empty-card .btn{ text-decoration: none; }
</style>
