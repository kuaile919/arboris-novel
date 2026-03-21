<!-- AIMETA P=势力编辑器_势力信息编辑|R=势力CRUD|NR=不含角色编辑|E=component:FactionsEditor|X=internal|A=编辑器|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-4 max-h-96 overflow-y-auto p-1">
    <div v-for="(faction, index) in localFactions" :key="index" class="p-4 border border-gray-200 rounded-lg bg-gray-50 relative">
      <button @click="removeFaction(index)" class="absolute top-2 right-2 text-red-400 hover:text-red-600 transition-colors p-1">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm4 0a1 1 0 012 0v6a1 1 0 11-2 0V8z" clip-rule="evenodd" />
        </svg>
      </button>
      <div class="mb-2">
        <label class="block text-sm font-medium text-gray-600 mb-1">阵营名称</label>
        <input
          type="text"
          v-model="faction.name"
          class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent"
          placeholder="例如：幽灵侦探林远"
        />
      </div>
      <div class="mb-2">
        <label class="block text-sm font-medium text-gray-600 mb-1">描述</label>
        <textarea
          v-model="faction.description"
          class="w-full h-20 p-2 mt-1 border border-gray-300 rounded-md focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition text-sm"
          placeholder="关于这个阵营的详细描述..."
        ></textarea>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-600 mb-1">首次出现章节</label>
        <input
          type="number"
          min="1"
          v-model.number="faction.first_appear_chapter"
          class="w-28 p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent text-sm"
          placeholder="章节号"
        />
      </div>
    </div>
    <button @click="addFaction" class="w-full mt-4 px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-md hover:bg-indigo-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
      + 添加新阵营
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';

interface Faction {
  name: string;
  description: string;
  first_appear_chapter?: number | null;
}

const props = defineProps({
  modelValue: {
    type: Array as () => Faction[],
    default: () => []
  }
});

const emit = defineEmits(['update:modelValue']);

const localFactions = ref<Faction[]>([]);
let syncing = false;

watch(() => props.modelValue, (newVal) => {
  syncing = true;
  localFactions.value = JSON.parse(JSON.stringify(newVal || []));
  nextTick(() => {
    syncing = false;
  });
}, { immediate: true });

watch(localFactions, (newVal) => {
  if (syncing) return;
  const cleaned = JSON.parse(JSON.stringify(newVal)).map((item: any) => ({
    ...item,
    first_appear_chapter: (item.first_appear_chapter === '' || item.first_appear_chapter === null || Number.isNaN(item.first_appear_chapter)) ? null : Number(item.first_appear_chapter)
  }))
  emit('update:modelValue', cleaned);
}, { deep: true });

const addFaction = () => {
  localFactions.value.push({ name: '', description: '', first_appear_chapter: null });
};

const removeFaction = (index: number) => {
  localFactions.value.splice(index, 1);
};
</script>
