<template>
  <span class="sc-avatar" :style="style">
    <span class="sc-avatar__image" :style="avatarStyle">
      <img v-if="src" :src="src" :alt="name" />
      <template v-else>{{ initials || "?" }}</template>
    </span>
    <span v-if="status" class="sc-avatar__status" :style="statusStyle" />
  </span>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  src: { type: String, default: "" },
  name: { type: String, default: "" },
  size: { type: String, default: "md" },
  square: { type: Boolean, default: false },
  status: { type: String, default: null },
  style: { type: Object, default: () => ({}) },
});

const sizes = { xs: 24, sm: 32, md: 40, lg: 48, xl: 64 };
const palette = ["var(--orange-500)", "var(--tomato-500)", "var(--basil-600)", "var(--honey-600)", "var(--blueberry-600)"];
const statusColors = {
  online: "var(--success)",
  busy: "var(--danger)",
  away: "var(--warning)",
  offline: "var(--text-subtle)",
};

const px = computed(() => sizes[props.size] || sizes.md);
const initials = computed(() =>
  props.name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase(),
);

const tint = computed(() => {
  let hash = 0;
  for (let index = 0; index < props.name.length; index += 1) {
    hash = (hash * 31 + props.name.charCodeAt(index)) % 997;
  }
  return palette[hash % palette.length];
});

const avatarStyle = computed(() => ({
  width: `${px.value}px`,
  height: `${px.value}px`,
  borderRadius: props.square ? "var(--radius-md)" : "50%",
  background: props.src ? "var(--surface-sunken)" : tint.value,
  font: `var(--weight-bold) ${Math.round(px.value * 0.36)}px/1 var(--font-sans)`,
}));

const statusStyle = computed(() => ({
  width: `${Math.max(8, px.value * 0.26)}px`,
  height: `${Math.max(8, px.value * 0.26)}px`,
  background: statusColors[props.status] || statusColors.offline,
}));
</script>

<style scoped>
.sc-avatar {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
}

.sc-avatar__image {
  color: #fff;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.06);
}

.sc-avatar__image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.sc-avatar__status {
  position: absolute;
  right: -1px;
  bottom: -1px;
  border-radius: 50%;
  border: 2px solid var(--surface-card);
}
</style>
