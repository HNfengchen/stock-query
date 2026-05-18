import { describe, it, expect } from 'vitest'
import { useAsyncState } from '../useAsyncState'

describe('useAsyncState', () => {
  it('creates initial state with idle status', () => {
    const { status, data, error } = useAsyncState()
    expect(status.value).toBe('idle')
    expect(data.value).toBeNull()
    expect(error.value).toBeNull()
  })

  it('creates initial state with provided initial data', () => {
    const { data } = useAsyncState('initial')
    expect(data.value).toBe('initial')
  })

  it('computed properties reflect idle state initially', () => {
    const { isIdle, isLoading, isSuccess, isError } = useAsyncState()
    expect(isIdle.value).toBe(true)
    expect(isLoading.value).toBe(false)
    expect(isSuccess.value).toBe(false)
    expect(isError.value).toBe(false)
  })
})

describe('useAsyncState transitions', () => {
  it('toLoading transitions to loading state', () => {
    const { status, isLoading, isIdle, toLoading } = useAsyncState<string>()
    toLoading()
    expect(status.value).toBe('loading')
    expect(isLoading.value).toBe(true)
    expect(isIdle.value).toBe(false)
  })

  it('toSuccess transitions to success state with data', () => {
    const { status, data, isSuccess, toSuccess } = useAsyncState<string>()
    toSuccess('result data')
    expect(status.value).toBe('success')
    expect(data.value).toBe('result data')
    expect(isSuccess.value).toBe(true)
  })

  it('toError transitions to error state with error message', () => {
    const { status, error, isError, toError } = useAsyncState<string>()
    toError('something failed')
    expect(status.value).toBe('error')
    expect(error.value).toBe('something failed')
    expect(isError.value).toBe(true)
  })

  it('reset returns to idle state with null data and error', () => {
    const { status, data, error, isIdle, toSuccess, reset } = useAsyncState<string>()
    toSuccess('some data')
    reset()
    expect(status.value).toBe('idle')
    expect(data.value).toBeNull()
    expect(error.value).toBeNull()
    expect(isIdle.value).toBe(true)
  })

  it('toLoading clears previous error', () => {
    const { error, isLoading, toError, toLoading } = useAsyncState<string>()
    toError('previous error')
    toLoading()
    expect(error.value).toBeNull()
    expect(isLoading.value).toBe(true)
  })

  it('toSuccess clears previous error', () => {
    const { error, isSuccess, toError, toSuccess } = useAsyncState<string>()
    toError('previous error')
    toSuccess('recovered')
    expect(error.value).toBeNull()
    expect(isSuccess.value).toBe(true)
  })
})

describe('useAsyncState execute', () => {
  it('executes async function and sets success state', async () => {
    const { status, data, isSuccess, execute } = useAsyncState<string>()
    const result = await execute(() => Promise.resolve('async result'))
    expect(result).toBe('async result')
    expect(status.value).toBe('success')
    expect(data.value).toBe('async result')
    expect(isSuccess.value).toBe(true)
  })

  it('sets error state when async function throws', async () => {
    const { status, error, isError, execute } = useAsyncState<string>()
    const result = await execute(() => Promise.reject(new Error('async error')))
    expect(result).toBeNull()
    expect(status.value).toBe('error')
    expect(error.value).toBe('async error')
    expect(isError.value).toBe(true)
  })

  it('transitions through loading before success', async () => {
    const { isLoading, execute } = useAsyncState<string>()
    let loadingDuringExecution = false
    const slowFn = () =>
      new Promise<string>((resolve) => {
        loadingDuringExecution = isLoading.value
        resolve('done')
      })
    await execute(slowFn)
    expect(loadingDuringExecution).toBe(true)
  })

  it('handles non-Error rejection by converting to string', async () => {
    const { error, isError, execute } = useAsyncState<string>()
    await execute(() => Promise.reject('string error'))
    expect(isError.value).toBe(true)
    expect(error.value).toBe('string error')
  })
})
