import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
})

// Attach JWT token if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 errors - try to refresh token
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // If 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const response = await axios.post(
            `${api.defaults.baseURL}/auth/token/refresh/`,
            { refresh: refreshToken }
          )

          const { access, refresh } = response.data
          localStorage.setItem('access_token', access)
          if (refresh) {
            localStorage.setItem('refresh_token', refresh)
          }

          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${access}`
          return api(originalRequest)
        } catch (refreshError) {
          // Refresh failed - clear tokens and redirect to login
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
          return Promise.reject(refreshError)
        }
      } else {
        // No refresh token - redirect to login
        window.location.href = '/login'
      }
    }

    return Promise.reject(error)
  }
)

// Auth helper functions
export const auth = {
  isAuthenticated: () => !!localStorage.getItem('access_token'),

  login: async (username, password) => {
    const response = await api.post('/auth/login/', { username, password })
    localStorage.setItem('access_token', response.data.access)
    localStorage.setItem('refresh_token', response.data.refresh)
    return response.data
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
  },

  getUser: () => {
    const token = localStorage.getItem('access_token')
    if (!token) return null
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      return payload
    } catch {
      return null
    }
  }
}

export default api
