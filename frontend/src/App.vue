<script setup>
import { ref, provide } from 'vue'
import Layout from './components/Layout.vue'

const currentGroup = ref(null)
const refreshKey = ref(0)

provide('currentGroup', currentGroup)
provide('triggerRefresh', () => refreshKey.value++)

function onGroupChange(group) {
  currentGroup.value = group
}
</script>

<template>
  <Layout :current-group="currentGroup" @group-change="onGroupChange">
    <router-view :key="refreshKey" />
  </Layout>
</template>
