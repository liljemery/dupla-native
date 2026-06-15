import { describe, expect, it, vi } from 'vitest'

import { debounce } from './debounce'

describe('debounce', () => {
  it('delays calls', async () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const d = debounce(fn, 100)
    d(1)
    d(2)
    expect(fn).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(100)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith(2)
    vi.useRealTimers()
  })
})
