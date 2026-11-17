import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fromQuery, sameQuery, toQuery } from './linkq.js'

// Keep a reactive object of filters and the page's link in step, both ways: a changed filter rewrites the link
// (replace, so Back still leaves the list), and a new link on the same view (a saved view, Back) sets the filters.
export function useLinkFilters(f, spec) {
  const route = useRoute()
  const router = useRouter()
  const path = route.path // a watcher outliving the view must not read another view's link
  const write = (v) => {
    const query = toQuery(v, spec, route.query)
    if (!sameQuery(query, route.query)) router.replace({ query, hash: route.hash })
  }
  Object.assign(f, fromQuery(route.query, spec))
  write(f) // a link with a value the list doesn't offer shows what the list really shows
  watch(() => ({ ...f }), write)
  watch(() => route.query, (q) => {
    if (route.path !== path) return
    const v = fromQuery(q, spec)
    if (Object.keys(spec).some((k) => v[k] !== f[k])) Object.assign(f, v)
  })
}
