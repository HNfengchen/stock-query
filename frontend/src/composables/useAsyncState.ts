import { shallowRef, computed } from 'vue'
import {
  createAsyncState,
  setLoading,
  setSuccess,
  setError,
  resetState,
} from '@/types/async-state'
import type { AsyncState, AsyncStatus } from '@/types/async-state'

export function useAsyncState<T>(initialData: T | null = null) {
  const state = shallowRef<AsyncState<T>>(createAsyncState<T>(initialData))

  const status = computed<AsyncStatus>(() => state.value.status)
  const data = computed<T | null>(() => state.value.data)
  const error = computed<string | null>(() => state.value.error)
  const isLoading = computed(() => state.value.status === 'loading')
  const isSuccess = computed(() => state.value.status === 'success')
  const isError = computed(() => state.value.status === 'error')
  const isIdle = computed(() => state.value.status === 'idle')

  function toLoading() {
    state.value = setLoading(state.value)
  }

  function toSuccess(result: T) {
    state.value = setSuccess(state.value, result)
  }

  function toError(err: string) {
    state.value = setError(state.value, err)
  }

  function reset() {
    state.value = resetState(state.value)
  }

  async function execute(asyncFn: () => Promise<T>): Promise<T | null> {
    toLoading()
    try {
      const result = await asyncFn()
      toSuccess(result)
      return result
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      toError(msg)
      return null
    }
  }

  return {
    state,
    status,
    data,
    error,
    isLoading,
    isSuccess,
    isError,
    isIdle,
    toLoading,
    toSuccess,
    toError,
    reset,
    execute,
  }
}
