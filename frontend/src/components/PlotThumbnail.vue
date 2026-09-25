<template>
  <SitePlan :plot="plot" :building="building" :width="width" :height="height" :scale="scale"
            :padding="padding" :tile-ground="ground" compact />
</template>

<script>
/* The small plan of a plot, the same wherever one is shown. See
 * lib/thumbnail.js for what it shows and why. */
import SitePlan from "./SitePlan.vue";
import { placement } from "../lib/store.js";
import { CARD_FRAME, THUMBNAIL_GROUND, THUMBNAIL_PADDING } from "../lib/thumbnail.js";

export default {
  name: "PlotThumbnail",
  components: { SitePlan },
  props: {
    plot: { type: Object, required: true },
    width: { type: Number, default: CARD_FRAME.width },
    height: { type: Number, default: CARD_FRAME.height },
    /** Pixels per metre shared with the thumbnails beside it. */
    scale: { type: Number, default: null }
  },
  data() {
    return { padding: THUMBNAIL_PADDING, ground: THUMBNAIL_GROUND };
  },
  computed: {
    building() { return placement(this.plot); }
  }
};
</script>
