<script setup lang="ts">
import { onMounted, ref } from "vue";

// The blueprint sheet beside the landing page's heading (docs/public/hero.svg). Safari keeps a
// loaded SVG image with its animation clock, so a reload or a return visit would show the drawing
// already finished. A fresh URL on every mount makes it a new image that draws itself again. It is
// added only in the browser, so a cached, finished copy never shows first.
const src = ref<string | null>(null);
onMounted(() => {
  src.value = `/hero.svg?drawn=${Date.now()}`;
});
</script>

<template>
  <img
    v-if="src"
    class="VPImage image-src"
    :src="src"
    alt="A blueprint sheet of linked capabilities"
  />
</template>
