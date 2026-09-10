/**
 * Signing in without leaving the page.
 *
 * The exchange is a chain of redirects across three origins, and a chain of
 * redirects cannot happen inside this document. It can happen in a window of
 * its own: the second window runs it, comes back to this origin on
 * `/anmeldung-fertig`, says so and closes. This page never unloads, so a
 * half-filled wizard, a dragged building and an unsaved note all survive
 * signing in -- which is the whole point, because the moment somebody wants
 * an account is usually the moment they have something to keep.
 *
 * Two things are deliberate:
 *
 * - **A blocked pop-up falls back to the old full navigation.** A browser may
 *   refuse the window, and a button that then does nothing is worse than a
 *   page change. `window.open` therefore has to be reached synchronously from
 *   the click, or every browser refuses it.
 * - **Whether it worked is asked of the backend, not read off the message.**
 *   The second window posting and closing is a race, and an abandoned window
 *   posts nothing at all. `/api/auth/me` knows either way.
 */
import { signInUrl } from "./api.js";
import { loadAccount, loadFromAccount, state } from "./store.js";

/** Where the second window lands when it is done. A route of this app. */
export const DONE_PATH = "/anmeldung-fertig";

/** What that page posts to the opener. Same-origin, and checked as such. */
export const SIGNED_IN = "where2build:anmeldung";

const WINDOW_NAME = "where2build-anmeldung";
const WINDOW_SIZE = "width=560,height=760";

/** Called by the page the second window lands on. */
export function reportSignedIn(target = window) {
  const opener = target.opener;
  if (!opener || opener.closed) return false;
  opener.postMessage(SIGNED_IN, target.location.origin);
  target.close();
  return true;
}

/** Resolves when the second window reports, or when it is gone. */
function settled(popup, view) {
  return new Promise(resolve => {
    let over = false;
    const finish = () => {
      if (over) return;
      over = true;
      view.removeEventListener("message", listen);
      clearInterval(watch);
      resolve();
    };
    const listen = event => {
      if (event.origin === view.location.origin && event.data === SIGNED_IN) finish();
    };
    view.addEventListener("message", listen);
    // A window closed by hand says nothing, so it is watched as well.
    const watch = setInterval(() => {
      if (popup.closed) finish();
    }, 400);
  });
}

/**
 * Start signing in. `back` is only for the fallback: it is where a full
 * navigation should return to, and is unused when the second window opens.
 *
 * Resolves to whether somebody is signed in afterwards.
 */
export async function beginSignIn(back = "/", view = window) {
  const popup = view.open(signInUrl(DONE_PATH), WINDOW_NAME, WINDOW_SIZE);
  if (!popup) {
    view.location.assign(signInUrl(back));
    return false;
  }
  await settled(popup, view);
  await loadAccount();
  // The account's copy follows the account, exactly as it does at start-up.
  await loadFromAccount();
  return state.account.angemeldet;
}
