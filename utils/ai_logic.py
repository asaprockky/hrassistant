import math

def sigmoid(x: float) -> float:
    """
    Sigmoid Activation Function:
    Squashes the weighted sum (z) into a probability range [0, 1].
    """
    return 1 / (1 + math.exp(-x))

def calculate_difficulty_score(failure_rate: float, time_spent: float) -> float:
    """
    Perceptron Logic:
    Calculates difficulty based on failure rate (w=0.8) and time pressure (w=0.2).
    """ 
    # 1. Weights and Bias (The 'Knowledge' of the neuron)
    w1 = 0.8  # Failure rate is the strongest indicator
    w2 = 0.2  # Time spent is a secondary indicator
    bias = -0.5 # Shift the activation so purely easy questions stay near 0
    
    # 2. Normalize Time Factor
    # We assume 60 seconds is 'max stress' (1.0). Cap it at 1.0.
    time_factor = min(time_spent / 60.0, 1.0)
    
    # 3. Weighted Sum (The 'Z' value)
    z = (w1 * failure_rate) + (w2 * time_factor) + bias
    
    # 4. Activation
    return sigmoid(z)