export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

export interface AsyncState<T> {
  status: AsyncStatus
  data: T | null
  error: string | null
}

export function createAsyncState<T>(initialData: T | null = null): AsyncState<T> {
  return {
    status: 'idle',
    data: initialData,
    error: null,
  }
}

export function setLoading<T>(state: AsyncState<T>): AsyncState<T> {
  return { ...state, status: 'loading', error: null }
}

export function setSuccess<T>(state: AsyncState<T>, data: T): AsyncState<T> {
  return { status: 'success', data, error: null }
}

export function setError<T>(state: AsyncState<T>, error: string): AsyncState<T> {
  return { ...state, status: 'error', error }
}

export function resetState<T>(state: AsyncState<T>): AsyncState<T> {
  return { status: 'idle', data: null, error: null }
}
