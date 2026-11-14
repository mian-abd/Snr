import '@testing-library/jest-dom/vitest'

// jsdom has no scrolling; navigation scrolls to the top.
window.scrollTo = () => {}
