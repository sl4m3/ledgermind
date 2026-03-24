import timeit

print(timeit.timeit("list(set([1,2,3] + [3,4,5]))", number=100000))
print(timeit.timeit("list(dict.fromkeys([1,2,3] + [3,4,5]))", number=100000))
