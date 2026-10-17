import { describe, expect, it } from 'vitest'

import { confidenceLabel, money, percent, relativeDays, titleCase } from '../lib/format'

describe('money', () => {
  it('formats with two decimals and a currency code', () => {
    expect(money(1234.5, 'AED')).toBe('AED 1,234.50')
    expect(money('61.75', 'USD')).toBe('USD 61.75')
  })

  it('renders a missing value as an em dash rather than zero', () => {
    expect(money(null, 'AED')).toBe('—')
    expect(money(undefined, 'AED')).toBe('—')
    expect(money('', 'AED')).toBe('—')
  })

  it('distinguishes a real zero from missing data', () => {
    expect(money(0, 'AED')).toBe('AED 0.00')
  })

  it('uses a true minus sign for negatives', () => {
    expect(money(-2310.4, 'AED')).toBe('AED −2,310.40')
  })

  it('can show an explicit plus sign for gains', () => {
    expect(money(120, 'AED', { signed: true })).toBe('AED +120.00')
    expect(money(-120, 'AED', { signed: true })).toBe('AED −120.00')
  })

  it('compacts large axis values', () => {
    expect(money(12500, undefined, { compact: true })).toBe('13K')
  })
})

describe('other formatters', () => {
  it('formats percentages and handles missing input', () => {
    expect(percent(10.27, 1)).toBe('10.3%')
    expect(percent(null)).toBe('—')
  })

  it('describes relative due dates in plain language', () => {
    expect(relativeDays(0)).toBe('today')
    expect(relativeDays(1)).toBe('tomorrow')
    expect(relativeDays(9)).toBe('in 9 days')
    expect(relativeDays(-3)).toBe('3 days ago')
  })

  it('turns snake_case keys into readable labels', () => {
    expect(titleCase('same_service_duplicate')).toBe('Same Service Duplicate')
    expect(titleCase('video_streaming')).toBe('Video Streaming')
  })

  it('maps confidence scores to words', () => {
    expect(confidenceLabel(0.94)).toBe('High confidence')
    expect(confidenceLabel(0.62)).toBe('Moderate confidence')
    expect(confidenceLabel(0.45)).toBe('Low confidence')
    expect(confidenceLabel(0.2)).toBe('Very low confidence')
  })
})
