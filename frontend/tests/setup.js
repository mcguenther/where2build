/** jsdom has no scrollTo; the views call it on every navigation. */
window.scrollTo = () => {};
