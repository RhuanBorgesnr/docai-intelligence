/**
 * WebGL feature detection.
 *
 * Returns true when the browser can create a WebGL2 (or WebGL1) context.
 * Memoises the result so the canvas element is created at most once.
 */
let _result = null

export function supportsWebGL() {
  if (_result !== null) return _result
  try {
    const canvas = document.createElement('canvas')
    _result = !!(
      canvas.getContext('webgl2') || canvas.getContext('webgl')
    )
  } catch {
    _result = false
  }
  return _result
}
