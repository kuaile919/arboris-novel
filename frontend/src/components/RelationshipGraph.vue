<!-- AIMETA P=关系图谱_树形可视化|R=层级树布局与布局切换|NR=关系悬浮信息增强|E=component:RelationshipGraph|X=ui|A=图谱组件|D=vue|S=dom -->
<template>
  <div class="relationship-graph-container">
    <div ref="networkContainer" class="network-canvas"></div>

    <div v-if="hasData" class="layout-controls">
      <button class="layout-btn" :class="{ active: layoutMode === 'LR' }" title="从左到右" @click="setLayoutMode('LR')">
        左到右
      </button>
      <button class="layout-btn" :class="{ active: layoutMode === 'UD' }" title="从上到下" @click="setLayoutMode('UD')">
        上到下
      </button>
    </div>

    <div v-if="hasData" class="zoom-controls">
      <button @click="zoomIn" class="zoom-btn" title="放大">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"></circle>
          <path d="M21 21l-4.35-4.35"></path>
          <line x1="11" y1="8" x2="11" y2="14"></line>
          <line x1="8" y1="11" x2="14" y2="11"></line>
        </svg>
      </button>
      <button @click="zoomOut" class="zoom-btn" title="缩小">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"></circle>
          <path d="M21 21l-4.35-4.35"></path>
          <line x1="8" y1="11" x2="14" y2="11"></line>
        </svg>
      </button>
      <button @click="fitView" class="zoom-btn" title="适应视图">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
        </svg>
      </button>
    </div>

    <div v-if="hasData" class="legend">
      <div class="legend-item">
        <span class="legend-line solid"></span>
        <span class="legend-text">主角相关关系</span>
      </div>
      <div class="legend-item">
        <span class="legend-line dashed"></span>
        <span class="legend-text">其他关系</span>
      </div>
    </div>

    <div v-if="!hasData" class="empty-state">
      <svg class="w-16 h-16 text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
      <p class="text-slate-500">暂无人物关系数据</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Network } from 'vis-network/standalone'
import type { Data, Edge, Node, Options } from 'vis-network/standalone'

interface RelationshipItem {
  character_from?: string
  character_to?: string
  relationship_type?: string
  description?: string
}

interface Props {
  relationships: RelationshipItem[]
  protagonists?: string[]
  protagonist?: string
}

const props = withDefaults(defineProps<Props>(), {
  relationships: () => [],
  protagonists: () => [],
  protagonist: ''
})

const networkContainer = ref<HTMLElement | null>(null)
const hasData = ref(false)
const layoutMode = ref<'LR' | 'UD'>('LR')
let network: Network | null = null

const HIGH_DENSITY_THRESHOLD = 8

const collectCharacters = () => {
  const nodeSet = new Set<string>()
  props.relationships.forEach((rel) => {
    if (rel.character_from) nodeSet.add(rel.character_from)
    if (rel.character_to) nodeSet.add(rel.character_to)
  })
  return nodeSet
}

const resolveMainCharacters = (nodeSet: Set<string>) => {
  let mains = props.protagonists.filter((name) => nodeSet.has(name))

  if (mains.length === 0 && props.protagonist && nodeSet.has(props.protagonist)) {
    mains = [props.protagonist]
  }

  if (mains.length === 0 && nodeSet.size > 0) {
    const count = new Map<string, number>()
    props.relationships.forEach((rel) => {
      if (rel.character_from) {
        count.set(rel.character_from, (count.get(rel.character_from) || 0) + 1)
      }
      if (rel.character_to) {
        count.set(rel.character_to, (count.get(rel.character_to) || 0) + 1)
      }
    })
    const fallback = Array.from(count.entries()).sort((a, b) => b[1] - a[1])[0]?.[0]
    if (fallback) mains = [fallback]
  }

  return mains
}

const buildEdgeTooltipElement = (rel: RelationshipItem) => {
  const wrap = document.createElement('div')
  wrap.className = 'rel-tooltip'

  const title = document.createElement('div')
  title.className = 'rel-tooltip-title'
  title.textContent = `${rel.character_from || '未知角色'} → ${rel.character_to || '未知角色'}`

  const rowType = document.createElement('div')
  rowType.className = 'rel-tooltip-row'
  const typeKey = document.createElement('span')
  typeKey.className = 'k'
  typeKey.textContent = '关系'
  const typeVal = document.createElement('span')
  typeVal.className = 'v'
  typeVal.textContent = rel.relationship_type || '未标注'
  rowType.append(typeKey, typeVal)

  const rowDesc = document.createElement('div')
  rowDesc.className = 'rel-tooltip-row'
  const descKey = document.createElement('span')
  descKey.className = 'k'
  descKey.textContent = '说明'
  const descVal = document.createElement('span')
  descVal.className = 'v'
  descVal.textContent = rel.description || '暂无详细描述'
  rowDesc.append(descKey, descVal)

  wrap.append(title, rowType, rowDesc)
  return wrap
}

const buildLevelMap = (allCharacters: string[], mainCharacters: string[]) => {
  const adjacency = new Map<string, Set<string>>()
  allCharacters.forEach((name) => adjacency.set(name, new Set()))

  props.relationships.forEach((rel) => {
    if (!rel.character_from || !rel.character_to) return
    adjacency.get(rel.character_from)?.add(rel.character_to)
    adjacency.get(rel.character_to)?.add(rel.character_from)
  })

  const mainSet = new Set(mainCharacters)
  const hasSecondaryRelations = props.relationships.some((rel) => {
    if (!rel.character_from || !rel.character_to) return false
    return !mainSet.has(rel.character_from) && !mainSet.has(rel.character_to)
  })

  const levelMap = new Map<string, number>()
  const distanceMap = new Map<string, number>()
  const sideMap = new Map<string, -1 | 0 | 1>()
  const queue: string[] = []

  mainCharacters.forEach((name) => {
    distanceMap.set(name, 0)
    sideMap.set(name, 0)
    queue.push(name)
  })

  const mainNeighbors = new Set<string>()
  mainCharacters.forEach((root) => {
    adjacency.get(root)?.forEach((name) => {
      if (!mainSet.has(name)) mainNeighbors.add(name)
    })
  })

  const useBalancedHorizontal =
    layoutMode.value === 'LR' &&
    mainNeighbors.size >= HIGH_DENSITY_THRESHOLD &&
    !hasSecondaryRelations

  const neighborOrder = Array.from(mainNeighbors).sort((a, b) => {
    const da = adjacency.get(a)?.size || 0
    const db = adjacency.get(b)?.size || 0
    return db - da
  })

  const neighborSide = new Map<string, -1 | 1>()
  neighborOrder.forEach((name, index) => {
    neighborSide.set(name, useBalancedHorizontal ? (index % 2 === 0 ? 1 : -1) : 1)
  })

  while (queue.length > 0) {
    const current = queue.shift() as string
    const currentDistance = distanceMap.get(current) ?? 0
    const currentSide = sideMap.get(current) ?? 1

    adjacency.get(current)?.forEach((neighbor) => {
      if (distanceMap.has(neighbor)) return

      const nextDistance = currentDistance + 1
      const nextSide = currentSide === 0 ? (neighborSide.get(neighbor) || 1) : currentSide

      distanceMap.set(neighbor, nextDistance)
      sideMap.set(neighbor, nextSide)
      queue.push(neighbor)
    })
  }

  let maxDistance = Math.max(0, ...Array.from(distanceMap.values()))
  allCharacters.forEach((name) => {
    if (!distanceMap.has(name)) {
      maxDistance += 1
      distanceMap.set(name, maxDistance)
      sideMap.set(name, 1)
    }
  })

  allCharacters.forEach((name) => {
    const distance = distanceMap.get(name) ?? 1
    const side = sideMap.get(name) ?? 1
    const level = layoutMode.value === 'LR' ? (side === 0 ? 0 : side * distance) : distance
    levelMap.set(name, level)
  })

  return levelMap
}

const buildGraphData = (): Data => {
  const nodes: Node[] = []
  const edges: Edge[] = []

  const nodeSet = collectCharacters()
  const allCharacters = Array.from(nodeSet)
  const mainCharacters = resolveMainCharacters(nodeSet)
  const mainSet = new Set(mainCharacters)
  const levelMap = buildLevelMap(allCharacters, mainCharacters)

  allCharacters.forEach((name) => {
    const isMain = mainSet.has(name)
    const level = levelMap.get(name) ?? 1

    nodes.push({
      id: name,
      label: name,
      shape: 'dot',
      level,
      size: isMain ? 52 : 32,
      color: isMain
        ? {
            background: '#7c3aed',
            border: '#5b21b6',
            highlight: {
              background: '#8b5cf6',
              border: '#7c3aed'
            }
          }
        : {
            background: '#0ea5e9',
            border: '#0284c7',
            highlight: {
              background: '#38bdf8',
              border: '#0ea5e9'
            }
          },
      font: {
        size: isMain ? 22 : 16,
        color: isMain ? '#1e1b4b' : '#0c4a6e',
        face: '"Noto Serif SC", "Source Han Serif SC", serif',
        bold: isMain ? ('bold' as const) : undefined
      },
      borderWidth: isMain ? 4 : 3,
      shadow: {
        enabled: true,
        color: isMain ? 'rgba(124, 58, 237, 0.45)' : 'rgba(14, 165, 233, 0.32)',
        size: isMain ? 24 : 14,
        x: 0,
        y: 6
      }
    })
  })

  props.relationships.forEach((rel, index) => {
    if (!rel.character_from || !rel.character_to) return

    const isMainRelated = mainSet.has(rel.character_from) || mainSet.has(rel.character_to)

    edges.push({
      id: `edge-${index}`,
      from: rel.character_from,
      to: rel.character_to,
      label: rel.relationship_type || '',
      arrows: {
        to: {
          enabled: true,
          scaleFactor: 0.75,
          type: 'arrow'
        }
      },
      color: {
        color: isMainRelated ? '#7c3aed' : '#94a3b8',
        highlight: '#ec4899',
        hover: '#ec4899',
        opacity: isMainRelated ? 0.92 : 0.62
      },
      font: {
        size: 12,
        color: isMainRelated ? '#4c1d95' : '#475569',
        face: '"Noto Sans SC", sans-serif',
        strokeWidth: 3,
        strokeColor: '#ffffff',
        background: 'rgba(255, 255, 255, 0.92)',
        align: 'middle'
      },
      smooth: {
        enabled: true,
        type: 'cubicBezier',
        forceDirection: layoutMode.value === 'LR' ? 'horizontal' : 'vertical',
        roundness: 0.42
      },
      width: isMainRelated ? 3 : 1.5,
      title: buildEdgeTooltipElement(rel),
      dashes: !isMainRelated
    })
  })

  hasData.value = nodes.length > 0
  return { nodes, edges }
}

const initNetwork = () => {
  if (!networkContainer.value) return

  const data = buildGraphData()

  const options: Options = {
    nodes: {
      borderWidth: 2,
      borderWidthSelected: 4
    },
    edges: {
      width: 2,
      selectionWidth: 4,
      hoverWidth: 3,
      smooth: {
        enabled: true,
        type: 'cubicBezier',
        forceDirection: layoutMode.value === 'LR' ? 'horizontal' : 'vertical',
        roundness: 0.42
      }
    },
    physics: {
      enabled: false
    },
    interaction: {
      hover: true,
      tooltipDelay: 120,
      zoomView: true,
      dragView: true,
      dragNodes: false,
      navigationButtons: false,
      keyboard: {
        enabled: true
      },
      zoomSpeed: 0.8
    },
    layout: {
      improvedLayout: true,
      hierarchical: {
        enabled: true,
        direction: layoutMode.value,
        sortMethod: 'hubsize',
        levelSeparation: 200,
        nodeSpacing: layoutMode.value === 'LR' ? 120 : 150,
        treeSpacing: 180,
        blockShifting: true,
        edgeMinimization: true,
        parentCentralization: true,
        shakeTowards: 'roots'
      }
    }
  }

  network = new Network(networkContainer.value, data, options)

  setTimeout(() => {
    if (!network) return
    network.fit({
      animation: {
        duration: 500,
        easingFunction: 'easeInOutQuad'
      }
    })
  }, 80)
}

const zoomIn = () => {
  if (!network) return
  const scale = network.getScale() * 1.2
  network.moveTo({ scale })
}

const zoomOut = () => {
  if (!network) return
  const scale = network.getScale() / 1.2
  network.moveTo({ scale })
}

const fitView = () => {
  if (!network) return
  network.fit({
    animation: {
      duration: 500,
      easingFunction: 'easeInOutQuad'
    }
  })
}

const setLayoutMode = (mode: 'LR' | 'UD') => {
  if (layoutMode.value === mode) return
  layoutMode.value = mode
  nextTick(() => {
    if (network) network.destroy()
    initNetwork()
  })
}

watch(
  () => [props.relationships, props.protagonist, props.protagonists],
  () => {
    nextTick(() => {
      if (network) network.destroy()
      initNetwork()
    })
  },
  { deep: true }
)

const handleResize = () => {
  if (!network) return
  network.destroy()
  initNetwork()
}

onMounted(() => {
  initNetwork()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (network) {
    network.destroy()
    network = null
  }
})
</script>

<style scoped>
.relationship-graph-container {
  position: relative;
  width: 100%;
  height: 600px;
  background:
    radial-gradient(circle at 16% 50%, rgba(124, 58, 237, 0.08) 0%, transparent 45%),
    linear-gradient(100deg, #faf5ff 0%, #f8fafc 45%, #eff6ff 100%);
  border-radius: 1.5rem;
  border: 1px solid rgba(124, 58, 237, 0.15);
  overflow: hidden;
  box-shadow:
    0 4px 6px rgba(0, 0, 0, 0.02),
    0 12px 40px rgba(124, 58, 237, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.relationship-graph-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    repeating-linear-gradient(
      90deg,
      rgba(148, 163, 184, 0.08) 0px,
      rgba(148, 163, 184, 0.08) 1px,
      transparent 1px,
      transparent 42px
    );
  opacity: 0.38;
  pointer-events: none;
}

.network-canvas {
  width: 100%;
  height: 100%;
  position: relative;
  z-index: 1;
}

.empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  z-index: 2;
}

.empty-state svg {
  filter: drop-shadow(0 4px 12px rgba(124, 58, 237, 0.15));
  animation: float 3s ease-in-out infinite;
}

.empty-state p {
  font-family: "Noto Sans SC", sans-serif;
  font-size: 15px;
  color: #64748b;
  letter-spacing: 0.02em;
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0px);
  }
  50% {
    transform: translateY(-10px);
  }
}

.layout-controls {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 10;
  display: flex;
  gap: 8px;
  padding: 6px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(124, 58, 237, 0.16);
  box-shadow: 0 2px 10px rgba(124, 58, 237, 0.12);
}

.layout-btn {
  min-width: 74px;
  height: 32px;
  border-radius: 9px;
  border: 1px solid transparent;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 12px;
  font-family: "Noto Sans SC", sans-serif;
  cursor: pointer;
  transition: all 0.18s ease;
}

.layout-btn:hover {
  border-color: rgba(99, 102, 241, 0.35);
  color: #4338ca;
  background: #eef2ff;
}

.layout-btn.active {
  background: #ede9fe;
  border-color: rgba(124, 58, 237, 0.45);
  color: #5b21b6;
  font-weight: 600;
}

.zoom-controls {
  position: absolute;
  bottom: 20px;
  right: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 10;
}

.zoom-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(124, 58, 237, 0.2);
  color: #5b21b6;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(124, 58, 237, 0.15);
}

.zoom-btn:hover {
  background: #7c3aed;
  color: white;
  transform: scale(1.05);
}

.zoom-btn:active {
  transform: scale(0.95);
}

.legend {
  position: absolute;
  top: 20px;
  left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.95);
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid rgba(124, 58, 237, 0.15);
  box-shadow: 0 2px 8px rgba(124, 58, 237, 0.1);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.legend-line {
  width: 30px;
  height: 3px;
  border-radius: 2px;
}

.legend-line.solid {
  background: #7c3aed;
}

.legend-line.dashed {
  background: repeating-linear-gradient(90deg, #94a3b8 0px, #94a3b8 6px, transparent 6px, transparent 10px);
}

.legend-text {
  font-size: 12px;
  color: #475569;
  font-family: "Noto Sans SC", sans-serif;
}

:deep(.vis-tooltip) {
  background: rgba(255, 255, 255, 0.98) !important;
  border: 1px solid rgba(124, 58, 237, 0.25) !important;
  border-radius: 12px !important;
  padding: 12px 16px !important;
  font-family: "Noto Sans SC", sans-serif !important;
  font-size: 13px !important;
  color: #334155 !important;
  box-shadow: 0 8px 24px rgba(124, 58, 237, 0.2) !important;
  backdrop-filter: blur(10px) !important;
  max-width: 360px !important;
  line-height: 1.5 !important;
  white-space: normal !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}

:deep(.rel-tooltip) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

:deep(.rel-tooltip-title) {
  font-size: 13px;
  font-weight: 700;
  color: #312e81;
}

:deep(.rel-tooltip-row) {
  display: flex;
  gap: 8px;
}

:deep(.rel-tooltip-row .k) {
  min-width: 32px;
  color: #6366f1;
  font-weight: 600;
}

:deep(.rel-tooltip-row .v) {
  flex: 1;
  color: #334155;
}
</style>