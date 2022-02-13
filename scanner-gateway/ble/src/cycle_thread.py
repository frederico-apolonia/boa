from threading import Thread
from time import sleep

class CycleThread(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.running = False
        self.elapsed_time = 0
    
    def run(self):
        self.running = True
        while self.running:
            self.elapsed_time += 1
            if self.elapsed_time == 60:
                self.elapsed_time = 0
            sleep(1)

    def stop(self):
        self.running = False

    def get_elapsed_time(self):
        return self.elapsed_time