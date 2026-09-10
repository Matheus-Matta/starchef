<template>
  <div :class="['image-upload', `image-upload--${variant}`]">
    <template v-if="variant === 'avatar'">
      <div class="image-upload__avatar">
        <img v-if="avatarItem" :src="avatarItem.url" :alt="label" />
        <i v-else class="pi pi-image" aria-hidden="true" />
      </div>
      <FileUpload
        v-if="!readonly"
        ref="uploader"
        mode="basic"
        :name="name"
        :accept="accept"
        :max-file-size="maxFileSize"
        custom-upload
        :choose-label="avatarItem ? 'Trocar imagem' : 'Escolher imagem'"
        choose-icon="pi pi-camera"
        @select="onSelect"
      />
      <Button
        v-if="!readonly && selectedFiles.length"
        type="button"
        label="Cancelar troca"
        icon="pi pi-times"
        severity="secondary"
        text
        size="small"
        @click="removeNew(0)"
      />
      <small v-if="!readonly">JPG, JPEG ou PNG. Clique para escolher uma nova imagem.</small>
    </template>

    <template v-else>
      <FileUpload
        v-if="!readonly"
        ref="uploader"
        :name="name"
        multiple
        :accept="accept"
        :max-file-size="maxFileSize"
        :file-limit="fileLimit"
        custom-upload
        :show-upload-button="false"
        :show-cancel-button="false"
        @select="onSelect"
      >
        <template #header="{ chooseCallback }">
          <div class="image-upload__toolbar">
            <Button type="button" label="Adicionar imagens" icon="pi pi-plus" @click="chooseCallback()" />
            <span>JPG, JPEG ou PNG · até {{ fileLimit }} imagens</span>
          </div>
        </template>
        <template #content>
          <div v-if="galleryItems.length" class="image-upload__gallery">
            <article v-for="item in galleryItems" :key="item.key" class="image-upload__card">
              <img :src="item.url" :alt="item.name || label" />
              <div class="image-upload__card-info">
                <strong>{{ item.name || 'Imagem cadastrada' }}</strong>
                <span>{{ item.kind === 'new' ? 'Nova imagem' : 'Salva' }}</span>
              </div>
              <Button
                type="button"
                class="image-upload__delete"
                icon="pi pi-trash"
                severity="danger"
                text
                rounded
                :aria-label="`Excluir ${item.name || 'imagem'}`"
                @click="removeItem(item)"
              />
            </article>
          </div>
        </template>
        <template #empty><DropMessage v-if="!galleryItems.length" /></template>
      </FileUpload>

      <div v-if="readonly && galleryItems.length" class="image-upload__readonly">
        <div class="image-upload__gallery">
          <article v-for="item in galleryItems" :key="item.key" class="image-upload__card">
            <img :src="item.url" :alt="item.name || label" />
            <div class="image-upload__card-info">
              <strong>{{ item.name || 'Imagem cadastrada' }}</strong>
              <span>Salva</span>
            </div>
          </article>
        </div>
      </div>
      <div v-else-if="readonly" class="image-upload__empty">Nenhuma imagem cadastrada.</div>
    </template>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onUnmounted, ref, watch } from "vue";
import Button from "primevue/button";
import FileUpload from "primevue/fileupload";

const DropMessage = defineComponent(() => () => h("div", { class: "image-upload__drop" }, [
  h("i", { class: "pi pi-cloud-upload" }),
  h("strong", "Arraste e solte as imagens aqui"),
]));

const props = defineProps({
  modelValue: { type: [File, Array], default: null },
  existing: { type: [String, Array, Object], default: null },
  removedIds: { type: Array, default: () => [] },
  name: { type: String, required: true },
  label: { type: String, default: "Imagem" },
  variant: { type: String, default: "avatar" },
  readonly: { type: Boolean, default: false },
  accept: { type: String, default: ".jpg,.jpeg,.png,image/jpeg,image/png" },
  maxFileSize: { type: Number, default: 8 * 1024 * 1024 },
  fileLimit: { type: Number, default: 20 },
});
const emit = defineEmits(["update:modelValue", "update:removedIds"]);
const uploader = ref(null);
const objectUrls = ref([]);
const selectedFiles = computed(() => Array.isArray(props.modelValue)
  ? props.modelValue
  : (props.modelValue instanceof File ? [props.modelValue] : []));

watch(selectedFiles, (files) => {
  objectUrls.value.forEach(URL.revokeObjectURL);
  objectUrls.value = files.map(URL.createObjectURL);
}, { immediate: true });
onUnmounted(() => objectUrls.value.forEach(URL.revokeObjectURL));

const savedItems = computed(() => {
  const values = Array.isArray(props.existing) ? props.existing : [props.existing];
  return values.filter(Boolean).map((item, index) => ({
    key: `saved-${item.id || index}`,
    id: typeof item === "string" ? null : item.id,
    url: typeof item === "string" ? item : item.url,
    name: typeof item === "string" ? "" : item.original_name,
    kind: "saved",
  })).filter((item) => item.url && !props.removedIds.includes(item.id));
});
const newItems = computed(() => selectedFiles.value.map((file, index) => ({
  key: `new-${file.name}-${file.size}-${file.lastModified}`,
  url: objectUrls.value[index], name: file.name, kind: "new", index,
})));
const galleryItems = computed(() => [...savedItems.value, ...newItems.value]);
const avatarItem = computed(() => newItems.value.at(-1) || savedItems.value[0] || null);

function onSelect(event) {
  const incoming = Array.from(event.files || []);
  if (props.variant === "gallery") {
    const unique = [...selectedFiles.value, ...incoming].filter((file, index, all) =>
      all.findIndex((other) => file.name === other.name && file.size === other.size) === index);
    emit("update:modelValue", unique.slice(0, props.fileLimit));
  } else {
    emit("update:modelValue", incoming.at(-1) || null);
  }
  queueMicrotask(() => uploader.value?.clear());
}
function removeNew(index) {
  const files = selectedFiles.value.filter((_, current) => current !== index);
  emit("update:modelValue", props.variant === "gallery" ? files : null);
}
function removeItem(item) {
  if (item.kind === "new") removeNew(item.index);
  else if (item.id) emit("update:removedIds", [...new Set([...props.removedIds, item.id])]);
}
</script>

<style scoped src="./ImageUploadField.css"></style>
