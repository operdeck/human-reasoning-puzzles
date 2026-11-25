"""Independent search over bridge multiplicities, degree totals and connectivity."""

from ..bridges import pair_name, parse


def solutions(text: str, limit: int = 2) -> list[dict[str, int]]:
    puzzle = parse(text)
    islands = list(puzzle.islands)
    positions = {cell: i for i, cell in enumerate(islands)}
    endpoints = [(positions[a], positions[b]) for a, b in puzzle.pairs]
    incident = [
        [i for i, pair in enumerate(endpoints) if vertex in pair] for vertex in range(len(islands))
    ]
    counts = [puzzle.islands[cell] for cell in islands]
    crossings = puzzle.crossings()
    found: list[dict[str, int]] = []

    def connected(domains: list[set[int]]) -> bool:
        adjacency: list[list[int]] = [[] for _ in islands]
        for (a, b), domain in zip(endpoints, domains, strict=True):
            if max(domain) > 0:
                adjacency[a].append(b)
                adjacency[b].append(a)
        reached = {0}
        todo = [0]
        while todo:
            for vertex in adjacency[todo.pop()]:
                if vertex not in reached:
                    reached.add(vertex)
                    todo.append(vertex)
        return len(reached) == len(islands)

    def propagate(domains: list[set[int]]) -> bool:
        changed = True
        while changed:
            changed = False
            for links, count in zip(incident, counts, strict=True):
                low = sum(min(domains[edge]) for edge in links)
                high = sum(max(domains[edge]) for edge in links)
                if not low <= count <= high:
                    return False
                for edge in links:
                    other_low = low - min(domains[edge])
                    other_high = high - max(domains[edge])
                    supported = {
                        value
                        for value in domains[edge]
                        if other_low + value <= count <= other_high + value
                    }
                    if not supported:
                        return False
                    if supported != domains[edge]:
                        domains[edge] = supported
                        changed = True
            for a, b in crossings:
                for first, second in ((a, b), (b, a)):
                    if min(domains[first]) > 0 and domains[second] != {0}:
                        if 0 not in domains[second]:
                            return False
                        domains[second] = {0}
                        changed = True
        return connected(domains)

    def search(domains: list[set[int]]) -> None:
        if len(found) >= limit or not propagate(domains):
            return
        choices = [edge for edge, domain in enumerate(domains) if len(domain) > 1]
        if not choices:
            found.append(
                {
                    pair_name(pair): next(iter(domain))
                    for pair, domain in zip(puzzle.pairs, domains, strict=True)
                }
            )
            return
        edge = min(
            choices,
            key=lambda candidate: (
                len(domains[candidate]),
                -sum(len(incident[node]) for node in endpoints[candidate]),
                candidate,
            ),
        )
        for value in sorted(domains[edge]):
            branch = [domain.copy() for domain in domains]
            branch[edge] = {value}
            search(branch)
            if len(found) >= limit:
                break

    if limit > 0:
        search([set(range(3)) for _ in puzzle.pairs])
    return found
