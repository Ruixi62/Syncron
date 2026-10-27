"""Algorithmes de graphe sur le graphe « objet -> ingrédients »."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable

Neighbors = Callable[[str], Iterable[str]]

_WHITE, _GRAY, _BLACK = 0, 1, 2


def find_cycles(roots: Iterable[str], neighbors: Neighbors) -> list[list[str]]:
    """DFS itératif. Retourne un cycle par arc retour rencontré, sous la forme
    [a, b, c, a]. Pas de récursion : aucune limite de profondeur Python."""
    color: dict[str, int] = {}
    cycles: list[list[str]] = []
    seen_cycles: set[frozenset[str]] = set()

    for root in roots:
        if color.get(root, _WHITE) != _WHITE:
            continue
        color[root] = _GRAY
        path = [root]
        stack = [iter(neighbors(root))]
        while stack:
            successor = next(stack[-1], None)
            if successor is None:
                stack.pop()
                color[path.pop()] = _BLACK
                continue
            state = color.get(successor, _WHITE)
            if state == _GRAY:
                cycle = [*path[path.index(successor) :], successor]
                signature = frozenset(cycle)
                if signature not in seen_cycles:
                    seen_cycles.add(signature)
                    cycles.append(cycle)
            elif state == _WHITE:
                color[successor] = _GRAY
                path.append(successor)
                stack.append(iter(neighbors(successor)))
    return cycles


def consumer_first_order(root: str, neighbors: Neighbors) -> list[str]:
    """Ordre topologique du sous-graphe atteignable depuis `root` dans lequel
    chaque objet apparaît APRÈS tous les objets qui le consomment.

    C'est la garantie qui permet au calculateur de connaître la demande
    totale d'un intermédiaire avant d'en calculer le nombre de crafts.
    Pré-condition : le sous-graphe est acyclique (vérifié par l'appelant).
    """
    reachable: list[str] = []
    visited = {root}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        reachable.append(node)
        for successor in neighbors(node):
            if successor not in visited:
                visited.add(successor)
                queue.append(successor)

    in_degree = dict.fromkeys(reachable, 0)
    for node in reachable:
        for successor in set(neighbors(node)):
            in_degree[successor] += 1

    order: list[str] = []
    ready = deque(node for node in reachable if in_degree[node] == 0)
    while ready:
        node = ready.popleft()
        order.append(node)
        for successor in dict.fromkeys(neighbors(node)):
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                ready.append(successor)
    return order
