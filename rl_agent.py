import numpy as np
import random
from collections import deque

class DQNAgent:
    def __init__(self, state_size, action_size):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = deque(maxlen=10000)

        self.gamma = 0.95
        self.epsilon = 1.0
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.997

        self.q_table = {}

    def _get_q(self, state):
        key = tuple(state.flatten())
        if key not in self.q_table:
            self.q_table[key] = np.zeros(self.action_size)
        return self.q_table[key]

    def act(self, state):
        if random.random() < self.epsilon:
            return random.randrange(self.action_size)
        return np.argmax(self._get_q(state))

    def remember(self, state, action, reward, next_state, done):
        key = tuple(state.flatten())
        next_key = tuple(next_state.flatten())

        if key not in self.q_table:
            self.q_table[key] = np.zeros(self.action_size)
        if next_key not in self.q_table:
            self.q_table[next_key] = np.zeros(self.action_size)

        target = reward
        if not done:
            target += self.gamma * np.max(self.q_table[next_key])

        self.q_table[key][action] += 0.1 * (target - self.q_table[key][action])

    def train(self, batch_size=32):
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
