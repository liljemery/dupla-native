import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PrimaryButton } from './PrimaryButton'

describe('PrimaryButton', () => {
  it('renders and handles click', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<PrimaryButton onClick={onClick}>Guardar</PrimaryButton>)
    const btn = await screen.findByRole('button', { name: /guardar/i })
    await user.click(btn)
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
