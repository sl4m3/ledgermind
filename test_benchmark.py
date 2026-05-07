from datetime import datetime
import timeit

def bench1():
    a = [1, 2, 3, 4]

def bench2():
    pass

if __name__ == "__main__":
    t1 = timeit.timeit(bench1, number=1000000)
    print(t1)
