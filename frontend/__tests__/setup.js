import '@testing-library/jest-dom'

// Mock IntersectionObserver for tests (not available in jsdom)
class MockIntersectionObserver {
  constructor() {
    this.observe = () => {}
    this.unobserve = () => {}
    this.disconnect = () => {}
  }
}
globalThis.IntersectionObserver = MockIntersectionObserver
