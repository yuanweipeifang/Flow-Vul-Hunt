import { useEffect, useState } from 'react'

export function useApiData<T>(loader: () => Promise<T>, deps: readonly unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    Promise.resolve()
      .then(() => {
        if (alive) setLoading(true)
      })
      .then(loader)
      .then((value) => {
        if (!alive) return
        setData(value)
        setError(null)
      })
      .catch((reason) => {
        if (!alive) return
        setData(null)
        setError(reason)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
    // 各页面会传入完整依赖数组，loader 由最新 render 闭包捕获。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error, loading }
}
