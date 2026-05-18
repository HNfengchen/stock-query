import { describe, it, expect } from 'vitest'
import {
  createAsyncState,
  setLoading,
  setSuccess,
  setError,
  resetState,
} from '../async-state'
import type { AsyncState } from '../async-state'

describe('createAsyncState', () => {
  it('creates initial state with null data by default', () => {
    const state = createAsyncState()
    expect(state.status).toBe('idle')
    expect(state.data).toBeNull()
    expect(state.error).toBeNull()
  })

  it('creates initial state with provided initial data', () => {
    const state = createAsyncState({ name: 'test' })
    expect(state.status).toBe('idle')
    expect(state.data).toEqual({ name: 'test' })
    expect(state.error).toBeNull()
  })

  it('creates initial state with null explicit initial data', () => {
    const state = createAsyncState<number>(null)
    expect(state.status).toBe('idle')
    expect(state.data).toBeNull()
    expect(state.error).toBeNull()
  })
})

describe('setLoading', () => {
  it('transitions idle state to loading', () => {
    const state = createAsyncState<string>()
    const next = setLoading(state)
    expect(next.status).toBe('loading')
    expect(next.error).toBeNull()
  })

  it('preserves data from previous state', () => {
    const state: AsyncState<string> = {
      status: 'success',
      data: 'existing',
      error: null,
    }
    const next = setLoading(state)
    expect(next.data).toBe('existing')
  })

  it('clears error from previous state', () => {
    const state: AsyncState<string> = {
      status: 'error',
      data: null,
      error: 'some error',
    }
    const next = setLoading(state)
    expect(next.error).toBeNull()
    expect(next.status).toBe('loading')
  })
})

describe('setSuccess', () => {
  it('transitions to success with data', () => {
    const state = createAsyncState<string>()
    const next = setSuccess(state, 'result')
    expect(next.status).toBe('success')
    expect(next.data).toBe('result')
    expect(next.error).toBeNull()
  })

  it('overwrites previous data', () => {
    const state: AsyncState<string> = {
      status: 'success',
      data: 'old',
      error: null,
    }
    const next = setSuccess(state, 'new')
    expect(next.data).toBe('new')
  })

  it('clears error from previous error state', () => {
    const state: AsyncState<number> = {
      status: 'error',
      data: null,
      error: 'failed',
    }
    const next = setSuccess(state, 42)
    expect(next.error).toBeNull()
    expect(next.data).toBe(42)
  })
})

describe('setError', () => {
  it('transitions to error with error message', () => {
    const state = createAsyncState()
    const next = setError(state, 'something went wrong')
    expect(next.status).toBe('error')
    expect(next.error).toBe('something went wrong')
  })

  it('preserves data from previous state', () => {
    const state: AsyncState<string> = {
      status: 'success',
      data: 'preserved',
      error: null,
    }
    const next = setError(state, 'error occurred')
    expect(next.data).toBe('preserved')
    expect(next.error).toBe('error occurred')
  })
})

describe('resetState', () => {
  it('resets to idle with null data and error', () => {
    const state: AsyncState<string> = {
      status: 'success',
      data: 'some data',
      error: null,
    }
    const next = resetState(state)
    expect(next.status).toBe('idle')
    expect(next.data).toBeNull()
    expect(next.error).toBeNull()
  })

  it('resets from error state', () => {
    const state: AsyncState<string> = {
      status: 'error',
      data: null,
      error: 'bad',
    }
    const next = resetState(state)
    expect(next.status).toBe('idle')
    expect(next.data).toBeNull()
    expect(next.error).toBeNull()
  })
})

describe('state transitions', () => {
  it('full lifecycle: idle -> loading -> success -> reset', () => {
    let state = createAsyncState<number>()
    expect(state.status).toBe('idle')

    state = setLoading(state)
    expect(state.status).toBe('loading')

    state = setSuccess(state, 100)
    expect(state.status).toBe('success')
    expect(state.data).toBe(100)

    state = resetState(state)
    expect(state.status).toBe('idle')
    expect(state.data).toBeNull()
  })

  it('full lifecycle: idle -> loading -> error -> loading -> success', () => {
    let state = createAsyncState<string>()

    state = setLoading(state)
    expect(state.status).toBe('loading')

    state = setError(state, 'network error')
    expect(state.status).toBe('error')
    expect(state.error).toBe('network error')

    state = setLoading(state)
    expect(state.status).toBe('loading')
    expect(state.error).toBeNull()

    state = setSuccess(state, 'recovered')
    expect(state.status).toBe('success')
    expect(state.data).toBe('recovered')
  })

  it('each transition returns a new object (immutability)', () => {
    const original = createAsyncState<string>()
    const loading = setLoading(original)
    const success = setSuccess(original, 'data')

    expect(original).not.toBe(loading)
    expect(original).not.toBe(success)
    expect(loading).not.toBe(success)
    expect(original.status).toBe('idle')
  })
})
